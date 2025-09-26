#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Enhanced robust generator: writes 1–2 posts/day from topics.yaml with SEO optimization and internal linking

Env:
  OPENAI_API_KEY       (required)
  POSTS_PER_RUN        default "2"
  MODEL_OUTLINE        default "gpt-5-mini"
  MODEL_DRAFT          default "gpt-5-mini"
  ALLOW_DUPLICATE_SLUG set "1"/"true" to allow timestamp-suffixed duplicates (default: skip)
  FAIL_ON_EMPTY        set "1"/"true" to exit non-zero if no posts were generated (default: succeed)
"""

import os, re, json, pathlib, time, sys, math
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone
import yaml

# Quality check imports (with fallbacks)
try:
    import textstat
    TEXTSTAT_AVAILABLE = True
except ImportError:
    TEXTSTAT_AVAILABLE = False

try:
    from fuzzywuzzy import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False

# --- Paths & config ---
REPO_ROOT       = pathlib.Path(__file__).resolve().parent.parent
CONTENT_DIR     = REPO_ROOT / "content" / "posts"
TOPICS_FILE     = REPO_ROOT / "data" / "topics.yaml"
TOPICS_DONE_FILE= REPO_ROOT / "data" / "topics_done.yaml"

def _int(env_name: str, default: int) -> int:
    try:
        return int(os.getenv(env_name, str(default)))
    except Exception:
        return default

POSTS_PER_RUN       = _int("POSTS_PER_RUN", 1)
MODEL_OUTLINE_ENV   = os.getenv("MODEL_OUTLINE", "gpt-4o-mini")
MODEL_DRAFT_ENV     = os.getenv("MODEL_DRAFT",   "gpt-4o-mini")
ALLOW_DUP_SLUG      = os.getenv("ALLOW_DUPLICATE_SLUG", "").strip().lower() in ("1","true","yes")
FAIL_ON_EMPTY       = os.getenv("FAIL_ON_EMPTY", "").strip().lower() in ("1","true","yes")

# Cost monitoring configuration
MAX_DAILY_COST_USD  = float(os.getenv("MAX_DAILY_COST_USD", "5.0"))  # Default $5/day limit
COST_LOG_FILE       = REPO_ROOT / "costs.log"

# Content quality thresholds
MIN_WORD_COUNT      = _int("MIN_WORD_COUNT", 1200)           # Minimum words for SEO
MAX_WORD_COUNT      = _int("MAX_WORD_COUNT", 3000)           # Maximum words to avoid bloat
TARGET_READING_LEVEL = _int("TARGET_READING_LEVEL", 12)      # Grade level (8-12 is good for business content)
MIN_SIMILARITY_THRESHOLD = _int("MIN_SIMILARITY_THRESHOLD", 85)  # % similarity to flag as duplicate
ENABLE_QUALITY_CHECKS = os.getenv("ENABLE_QUALITY_CHECKS", "1").lower() in ("1", "true", "yes")

# --- OpenAI client ---
try:
    from openai import OpenAI
    from openai._exceptions import (
        APITimeoutError, APIConnectionError, RateLimitError, APIError
    )
except Exception as e:
    raise SystemExit("Missing 'openai' package. In venv: pip install openai pyyaml") from e

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise SystemExit("OPENAI_API_KEY not set")

client = OpenAI(api_key=api_key, timeout=30.0)  # client-level timeout

# --- Helpers ---
def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-")[:80] or "post"

# Approximate token costs (as of 2025) - update these as needed
TOKEN_COSTS = {
    "gpt-4o": {"input": 0.0025, "output": 0.01},      # per 1K tokens
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4": {"input": 0.003, "output": 0.006},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
}

def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost based on model and token usage."""
    costs = TOKEN_COSTS.get(model, TOKEN_COSTS["gpt-4o-mini"])  # fallback
    return (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1000

def log_cost(model: str, estimated_cost: float, operation: str):
    """Log estimated cost to file with timestamp."""
    timestamp = datetime.now(timezone.utc).isoformat()
    log_entry = f"{timestamp},{model},{operation},{estimated_cost:.4f}\n"

    try:
        with open(COST_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        print(f"[warn] Could not log cost: {e}", file=sys.stderr)

def get_daily_cost() -> float:
    """Get today's estimated cost from log file."""
    if not COST_LOG_FILE.exists():
        return 0.0

    today = datetime.now(timezone.utc).date()
    daily_cost = 0.0

    try:
        with open(COST_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(",")
                if len(parts) >= 4:
                    timestamp_str = parts[0]
                    cost = float(parts[3])
                    log_date = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00")).date()
                    if log_date == today:
                        daily_cost += cost
    except Exception as e:
        print(f"[warn] Could not read cost log: {e}", file=sys.stderr)

    return daily_cost

# --- Content Quality Analysis ---

def analyze_readability(text: str) -> Dict[str, Any]:
    """Analyze text readability metrics."""
    if not TEXTSTAT_AVAILABLE:
        return {"error": "textstat not available"}

    # Strip markdown for accurate analysis
    plain_text = re.sub(r'[#*`\[\]()]', '', text)
    plain_text = re.sub(r'https?://[^\s]+', '', plain_text)

    return {
        "flesch_reading_ease": textstat.flesch_reading_ease(plain_text),
        "flesch_kincaid_grade": textstat.flesch_kincaid_grade(plain_text),
        "automated_readability_index": textstat.automated_readability_index(plain_text),
        "coleman_liau_index": textstat.coleman_liau_index(plain_text),
        "gunning_fog": textstat.gunning_fog(plain_text),
        "smog_index": textstat.smog_index(plain_text),
        "reading_time": textstat.reading_time(plain_text, ms_per_char=14.69),
        "sentence_count": textstat.sentence_count(plain_text),
        "word_count": len(plain_text.split()),
    }

def check_duplicate_content(new_content: str, existing_posts_dir: pathlib.Path) -> Tuple[bool, str, float]:
    """Check if content is too similar to existing posts."""
    if not FUZZY_AVAILABLE:
        return False, "", 0.0

    # Clean content for comparison
    new_clean = re.sub(r'[#*`\[\]()_-]', '', new_content.lower())
    new_clean = re.sub(r'https?://[^\s]+', '', new_clean)
    new_clean = ' '.join(new_clean.split())[:2000]  # First 2000 chars for comparison

    max_similarity = 0.0
    most_similar_file = ""

    for post_file in existing_posts_dir.glob("*.md"):
        if post_file.name.startswith("_"):
            continue

        try:
            existing_content = post_file.read_text(encoding="utf-8")
            # Remove front matter
            content_parts = existing_content.split("---", 2)
            if len(content_parts) >= 3:
                existing_body = content_parts[2]
            else:
                existing_body = existing_content

            existing_clean = re.sub(r'[#*`\[\]()_-]', '', existing_body.lower())
            existing_clean = re.sub(r'https?://[^\s]+', '', existing_clean)
            existing_clean = ' '.join(existing_clean.split())[:2000]

            similarity = fuzz.partial_ratio(new_clean, existing_clean)
            if similarity > max_similarity:
                max_similarity = similarity
                most_similar_file = post_file.name

        except Exception as e:
            print(f"[warn] Could not check similarity with {post_file.name}: {e}", file=sys.stderr)
            continue

    is_duplicate = max_similarity >= MIN_SIMILARITY_THRESHOLD
    return is_duplicate, most_similar_file, max_similarity

def check_content_flags(content: str) -> List[str]:
    """Check for potential content issues."""
    flags = []

    # Check for placeholder text
    placeholders = ["lorem ipsum", "[insert", "[add", "TODO", "FIXME", "placeholder"]
    content_lower = content.lower()
    for placeholder in placeholders:
        if placeholder in content_lower:
            flags.append(f"Contains placeholder text: '{placeholder}'")

    # Check for excessive repetition
    sentences = re.split(r'[.!?]+', content)
    sentence_counts = {}
    for sentence in sentences:
        clean_sentence = sentence.strip().lower()
        if len(clean_sentence) > 20:  # Only check substantial sentences
            if clean_sentence in sentence_counts:
                sentence_counts[clean_sentence] += 1
            else:
                sentence_counts[clean_sentence] = 1

    for sentence, count in sentence_counts.items():
        if count >= 3:
            flags.append(f"Repeated sentence ({count}x): '{sentence[:100]}...'")

    # Check for missing sections that should be present
    required_sections = ["##", "###"]  # Should have at least some headers
    if not any(section in content for section in required_sections):
        flags.append("Missing structured headers (H2/H3)")

    # Check for external links (good for authority)
    external_links = len(re.findall(r'\[([^\]]+)\]\(https?://(?!aibookkeepingtools\.com)[^\)]+\)', content))
    if external_links < 2:
        flags.append(f"Few external citations ({external_links}) - consider adding authoritative sources")

    return flags

def quality_check_content(content: str, title: str) -> Dict[str, Any]:
    """Perform comprehensive quality check on generated content."""
    results = {
        "title": title,
        "passed": True,
        "warnings": [],
        "errors": [],
        "metrics": {}
    }

    if not ENABLE_QUALITY_CHECKS:
        results["skipped"] = True
        return results

    # Basic metrics
    word_count = len(content.split())
    results["metrics"]["word_count"] = word_count

    # Word count validation
    if word_count < MIN_WORD_COUNT:
        results["errors"].append(f"Content too short: {word_count} words (minimum: {MIN_WORD_COUNT})")
        results["passed"] = False
    elif word_count > MAX_WORD_COUNT:
        results["warnings"].append(f"Content very long: {word_count} words (target: <{MAX_WORD_COUNT})")

    # Readability analysis
    if TEXTSTAT_AVAILABLE:
        readability = analyze_readability(content)
        results["metrics"]["readability"] = readability

        if "error" not in readability:
            grade_level = readability.get("flesch_kincaid_grade", 0)
            if grade_level > TARGET_READING_LEVEL + 2:
                results["warnings"].append(f"Reading level high: Grade {grade_level:.1f} (target: ~{TARGET_READING_LEVEL})")
            elif grade_level < TARGET_READING_LEVEL - 4:
                results["warnings"].append(f"Reading level low: Grade {grade_level:.1f} (target: ~{TARGET_READING_LEVEL})")

    # Content flags
    flags = check_content_flags(content)
    for flag in flags:
        if "placeholder" in flag.lower() or "missing" in flag.lower():
            results["errors"].append(flag)
            results["passed"] = False
        else:
            results["warnings"].append(flag)

    # Duplicate check
    if FUZZY_AVAILABLE:
        is_duplicate, similar_file, similarity = check_duplicate_content(content, CONTENT_DIR)
        results["metrics"]["similarity"] = {
            "is_duplicate": is_duplicate,
            "most_similar_file": similar_file,
            "max_similarity": similarity
        }

        if is_duplicate:
            results["errors"].append(f"Content too similar ({similarity:.1f}%) to existing post: {similar_file}")
            results["passed"] = False
        elif similarity > 70:
            results["warnings"].append(f"Content moderately similar ({similarity:.1f}%) to: {similar_file}")

    return results

def calculate_content_score(quality_results: Dict[str, Any]) -> Tuple[float, str]:
    """Calculate overall content quality score (0-100) and grade."""
    if not quality_results.get("passed", True):
        return 0.0, "F"

    score = 100.0
    metrics = quality_results.get("metrics", {})

    # Word count scoring (0-20 points)
    word_count = metrics.get("word_count", 0)
    if word_count < MIN_WORD_COUNT:
        score -= 20  # Major penalty for too short
    elif word_count > MAX_WORD_COUNT:
        score -= 10  # Moderate penalty for too long
    elif MIN_WORD_COUNT <= word_count <= 2000:
        score += 0  # Perfect range
    else:
        score -= 5  # Slight penalty for moderately long

    # Readability scoring (0-15 points)
    readability = metrics.get("readability", {})
    if readability and "error" not in readability:
        grade_level = readability.get("flesch_kincaid_grade", TARGET_READING_LEVEL)
        if abs(grade_level - TARGET_READING_LEVEL) <= 1:
            score += 0  # Perfect readability
        elif abs(grade_level - TARGET_READING_LEVEL) <= 3:
            score -= 5  # Slightly off target
        else:
            score -= 15  # Far from target

    # External links scoring (0-10 points)
    warnings = quality_results.get("warnings", [])
    few_citations = any("Few external citations" in w for w in warnings)
    if few_citations:
        score -= 10

    # Similarity penalty (0-15 points)
    similarity = metrics.get("similarity", {})
    if similarity:
        sim_score = similarity.get("max_similarity", 0)
        if sim_score > 80:
            score -= 15  # High similarity penalty
        elif sim_score > 70:
            score -= 10  # Moderate similarity penalty
        elif sim_score > 60:
            score -= 5   # Light similarity penalty

    # Warning penalties
    warning_count = len(warnings)
    score -= min(warning_count * 3, 15)  # Max 15 points penalty for warnings

    # Ensure score is within bounds
    score = max(0, min(100, score))

    # Grade assignment
    if score >= 90:
        grade = "A"
    elif score >= 80:
        grade = "B"
    elif score >= 70:
        grade = "C"
    elif score >= 60:
        grade = "D"
    else:
        grade = "F"

    return score, grade

def add_fact_checking_prompts() -> str:
    """Return additional prompts to encourage fact-checking."""
    return """

FACT-CHECKING REQUIREMENTS:
- Cite authoritative sources for all financial data, statistics, and regulatory information
- Use official vendor documentation for feature descriptions
- Reference IRS.gov, AICPA.org, or other regulatory bodies for compliance information
- Include publication dates for statistics (prefer data from 2024-2025)
- Verify pricing information is current
- Cross-reference tool capabilities with official product pages
"""

# Enhanced system prompt with internal linking
SYSTEM_EDITOR = (
    "You are a senior technical editor specializing in AI + bookkeeping/accounting. "
    "Write with precision and practical steps. Use Markdown with H2/H3, bullets, short paragraphs. "
    "Include 2-3 internal links to related content where natural and helpful. "
    "Cite 3–5 reputable sources inline (official docs, vendor docs, gov, recognized publishers). "
    "Avoid fluff and clickbait. Ensure accuracy. Focus on SEO best practices. "
    "FACT-CHECK: Verify all statistics, pricing, and feature claims against official sources. "
    "Include publication dates for data when possible. Use current (2024-2025) information."
)

# Enhanced outline prompt with existing content context
OUTLINE_PROMPT_TMPL = """Create a concise brief and outline for a post.

Topic/Keyword: {keyword}
Audience: {audience}
Search intent: {intent}

Existing content to reference (add internal links where relevant):
- "Best AI Bookkeeping Tools for Small Businesses 2025" (/posts/best-ai-bookkeeping-tools-for-small-businesses-2025/)
- "How to Automate Bookkeeping with AI: QuickBooks & Receipt OCR" (/posts/how-to-automate-bookkeeping-with-ai-quickbooks-receipt-ocr/)
- "AI Expense Tracking Apps Compared: Expensify vs Zoho vs Divvy" (/posts/ai-expense-tracking-apps-compared-expensify-vs-zoho-vs-divvy/)
- "AI for Accountants: Optimize Workflows to Serve More Clients" (/posts/ai-for-accountants-optimize-workflows-to-serve-more-clients/)
- "AI Tax Prep Tools for Self-Employed in 2025" (/posts/ai-tax-prep-tools-for-self-employed-in-2025/)

Return JSON with keys:
- working_title (<=70 chars, include the main keyword, add year if relevant)
- meta_description (150-155 chars, compelling with benefits)
- summary (2–3 sentences)
- outline (array of 8–12 section headings including "Quick Start" section)
- entities (10–20 important terms)
- faqs (5 short Q/A pairs)
- internal_link_opportunities (2-3 places where linking to existing content makes sense)
"""

# Enhanced draft prompt with SEO optimization
DRAFT_PROMPT_TMPL = """Write a 1,600–2,100 word article in Markdown optimized for SEO and user experience.

Working title: {working_title}

Summary:
{summary}

Outline:
{outline_md}

Guidelines:
- Include the target keyword naturally in the first 100 words and in H2 headings where appropriate
- Add 2-3 internal links to existing content where they provide genuine value:
  * /posts/best-ai-bookkeeping-tools-for-small-businesses-2025/
  * /posts/how-to-automate-bookkeeping-with-ai-quickbooks-receipt-ocr/
  * /posts/ai-expense-tracking-apps-compared-expensify-vs-zoho-vs-divvy/
  * /posts/ai-for-accountants-optimize-workflows-to-serve-more-clients/
  * /posts/ai-tax-prep-tools-for-self-employed-in-2025/
- Technical depth; step-by-step where applicable
- Include a short "Quick Start" section early in the post
- Add a "Common Mistakes to Avoid" or "Pitfalls & Gotchas" section
- Include 3–5 authoritative citations inline as Markdown links
- Add a 5-item FAQ at the end (use/refine provided Q/A)
- Use H2/H3 headings. Keep paragraphs short (2-3 sentences max)
- Include at least one comparison table or bulleted pros/cons list
- End with clear next steps or call-to-action
- FACT-CHECK all claims: Verify statistics, pricing, features against official sources
- Include publication dates for statistics and prefer 2024-2025 data
- Use authoritative citations: IRS.gov, vendor docs, industry reports from recognized publishers

Internal link format: [descriptive anchor text](/posts/slug-here/)

Return ONLY the Markdown body (no front matter, no backticks).
"""

def supports_json_mode(model: str) -> bool:
    return any(model.startswith(p) for p in ("gpt-4o", "gpt-4", "gpt-3.5"))

def _is_modern_model(model: str) -> bool:
    return model.startswith(("gpt-4o", "gpt-4"))

# --- Hardened API wrapper with retries/backoff ---
RETRYABLE = (APITimeoutError, APIConnectionError, RateLimitError, APIError)

def _sleep_backoff(attempt: int) -> None:
    delay = min(2 ** attempt, 30) + 0.25 * math.sin(attempt)  # jitter
    time.sleep(delay)

def chat_with_retry(
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int,
    timeout: int = 60,
    json_mode: bool = False,
    max_retries: int = 5,
    operation: str = "generation",
) -> str:
    kwargs: Dict[str, Any] = {"model": model, "messages": messages, "timeout": timeout}
    if json_mode and supports_json_mode(model):
        kwargs["response_format"] = {"type": "json_object"}

    if _is_modern_model(model):
        kwargs["max_completion_tokens"] = max_tokens
    else:
        kwargs["max_tokens"] = max_tokens
        kwargs["temperature"] = 1.0

    attempt = 0
    while True:
        try:
            resp = client.chat.completions.create(**kwargs)
            content = (resp.choices[0].message.content or "").strip()

            # Log estimated cost
            if resp.usage:
                input_tokens = resp.usage.prompt_tokens
                output_tokens = resp.usage.completion_tokens
                cost = estimate_cost(model, input_tokens, output_tokens)
                log_cost(model, cost, operation)
                print(f"[cost] {model} {operation}: ~${cost:.4f} (tokens: {input_tokens}+{output_tokens})")

            return content
        except RETRYABLE as e:
            attempt += 1
            if attempt > max_retries:
                print(f"[chat_call] {model} ({'json' if json_mode else 'plain'}) error: {repr(e)} (giving up)", file=sys.stderr)
                return ""
            print(f"[warn] API issue: {e.__class__.__name__} (attempt {attempt}/{max_retries}); backing off...", file=sys.stderr)
            _sleep_backoff(attempt)
        except Exception as e:
            print(f"[chat_call] {model} unexpected error: {repr(e)}", file=sys.stderr)
            return ""

def robust_json(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("empty response")
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if not m:
            raise
        return json.loads(m.group(0))

def backoff_sleep(i: int):
    time.sleep(min(2**i, 8))

def now_past_iso() -> str:
    # 5 minutes in the past, timezone-aware, with Z suffix for Hugo
    return (datetime.now(timezone.utc) - timedelta(minutes=5)) \
        .isoformat(timespec="seconds").replace("+00:00", "Z")

# --- Topics IO ---
def _yaml_read(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

def _yaml_write_atomic(path: pathlib.Path, data: dict):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    tmp.replace(path)

def load_topics() -> List[dict]:
    data = _yaml_read(TOPICS_FILE)
    return data.get("topics", [])

def save_topics(topics: List[dict]):
    _yaml_write_atomic(TOPICS_FILE, {"topics": topics})

def append_topic_done(record: dict):
    data = _yaml_read(TOPICS_DONE_FILE)
    done = data.get("topics_done", [])
    done.append(record)
    _yaml_write_atomic(TOPICS_DONE_FILE, {"topics_done": done})

def mark_topic_done(original_topic: dict, *, slug: str, title: str):
    """
    Remove the first matching topic (by keyword) from topics.yaml and
    append a record to topics_done.yaml with metadata.
    """
    kw = (original_topic.get("keyword") or "").strip()
    topics = load_topics()
    new_topics = []
    removed = False
    for t in topics:
        if not removed and (t.get("keyword") or "").strip() == kw:
            removed = True
            continue
        new_topics.append(t)
    if removed:
        save_topics(new_topics)
    append_topic_done({
        "keyword": kw,
        "slug": slug,
        "title": title,
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "audience": original_topic.get("audience"),
        "intent": original_topic.get("intent"),
    })

def existing_slugs() -> set:
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    return {p.stem for p in CONTENT_DIR.glob("*.md")}

def front_matter(title: str, slug: str, description: str, *, draft: bool=False) -> str:
    description = (description or f"{title} — a practical guide.").strip()
    if len(description) > 155:
        description = description[:152].rstrip() + "..."
    fm = {
        "title": title,
        "date": now_past_iso(),
        "slug": slug,
        "description": description,
        "tags": ["AI", "Bookkeeping", "Accounting", "Tools"],
        "categories": ["Guides"],
        "draft": draft,
    }
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(json.dumps(x) for x in v)}]")
        else:
            lines.append(f"{k}: {json.dumps(v)}")
    lines.append("---")
    return "\n".join(lines)

def write_post(slug: str, title: str, description: str, body_md: str, *, draft: bool=False):
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    out = CONTENT_DIR / f"{slug}.md"
    out.write_text(front_matter(title, slug, description, draft=draft) + "\n\n" + body_md.strip() + "\n", encoding="utf-8")
    print(f"Wrote: {out.relative_to(REPO_ROOT)}")

def get_outline(keyword: str, audience: str, intent: str) -> Optional[Dict[str, Any]]:
    """Try outline across models & modes with retries."""
    prompt = OUTLINE_PROMPT_TMPL.format(keyword=keyword, audience=audience, intent=intent)
    messages = [{"role": "system", "content": SYSTEM_EDITOR},
                {"role": "user", "content": prompt}]

    models_try = [MODEL_OUTLINE_ENV, "gpt-4o-mini", "gpt-4o"]
    tried = set()

    for model in models_try:
        if not model or model in tried:
            continue
        tried.add(model)

        # 1) JSON mode
        for attempt in range(3):
            txt = chat_with_retry(
                model=model,
                messages=messages,
                max_tokens=1000,
                timeout=45,
                json_mode=True,
                max_retries=5,
                operation="outline",
            )
            if txt:
                try:
                    return robust_json(txt)
                except Exception:
                    print(f"Failed JSON parse (model={model}, attempt={attempt+1}); first 200 chars:\n{txt[:200]}", file=sys.stderr)
            backoff_sleep(attempt)

        # 2) Plain mode, then extract JSON
        for attempt in range(3):
            txt = chat_with_retry(
                model=model,
                messages=messages,
                max_tokens=1000,
                timeout=45,
                json_mode=False,
                max_retries=5,
                operation="outline",
            )
            if txt:
                try:
                    return robust_json(txt)
                except Exception:
                    print(f"Failed plain-parse (model={model}, attempt={attempt+1}); first 200 chars:\n{txt[:200]}", file=sys.stderr)
            backoff_sleep(attempt)

    return None

def main():
    # Check daily cost limit
    daily_cost = get_daily_cost()
    print(f"[cost] Current daily spending: ${daily_cost:.4f} (limit: ${MAX_DAILY_COST_USD:.2f})")

    if daily_cost >= MAX_DAILY_COST_USD:
        print(f"[cost] Daily cost limit reached (${daily_cost:.4f} >= ${MAX_DAILY_COST_USD:.2f}). Skipping generation.")
        return

    topics = load_topics()
    used = existing_slugs()
    generated = 0

    for topic in (topics or []):
        if generated >= POSTS_PER_RUN:
            break

        keyword = (topic.get("keyword") or "").strip()
        if not keyword:
            continue
        audience = (topic.get("audience") or "Small business owners").strip()
        intent   = (topic.get("intent")   or "How-to tutorial").strip()

        # --- Outline ---
        plan = get_outline(keyword, audience, intent)
        if not plan:
            print(f"Outline failed for: {keyword}", file=sys.stderr)
            continue

        title   = (plan.get("working_title") or keyword.title()).strip()
        summary = (plan.get("summary") or "").strip()
        meta_description = (plan.get("meta_description") or summary).strip()
        outline_list = plan.get("outline") or []
        faqs = plan.get("faqs") or []

        base_slug = slugify(title) or slugify(keyword)

        # Duplicate handling
        if base_slug in used and not ALLOW_DUP_SLUG:
            print(f"[skip] Duplicate slug detected, skipping topic: {keyword!r} -> slug {base_slug!r}")
            # Also mark as done so it doesn't keep trying in future runs
            mark_topic_done(topic, slug=base_slug, title=title)
            continue
        if base_slug in used and ALLOW_DUP_SLUG:
            base_slug = f"{base_slug}-{int(datetime.now(timezone.utc).timestamp())}"

        slug = base_slug
        outline_md = "\n".join(f"- {h}" for h in outline_list) if outline_list else "- Introduction\n- Quick Start\n- Steps\n- Common Mistakes\n- Conclusion"

        # --- Draft ---
        draft_models = [MODEL_DRAFT_ENV, "gpt-4o-mini", "gpt-4o"]
        body_md = ""
        for model in draft_models:
            for attempt in range(3):
                body_md = chat_with_retry(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_EDITOR},
                        {"role": "user", "content": DRAFT_PROMPT_TMPL.format(
                            working_title=title, summary=summary, outline_md=outline_md)}
                    ],
                    max_tokens=2000,   # ~1.5–2k tokens output target
                    timeout=90,
                    json_mode=False,
                    max_retries=5,
                    operation="draft",
                )
                if body_md:
                    break
                backoff_sleep(attempt)
            if body_md:
                break

        if not body_md:
            print(f"Draft failed for: {title}", file=sys.stderr)
            continue

        # Quality check the generated content
        quality_results = quality_check_content(body_md, title)

        if not quality_results.get("passed", True):
            print(f"[quality] Content failed quality checks for: {title}")
            for error in quality_results.get("errors", []):
                print(f"  ERROR: {error}")
            # Skip this post - don't mark as done so it can be retried
            continue

        # Log quality warnings but continue
        warnings = quality_results.get("warnings", [])
        if warnings:
            print(f"[quality] Content warnings for: {title}")
            for warning in warnings:
                print(f"  WARN: {warning}")

        # Log quality metrics
        metrics = quality_results.get("metrics", {})
        if metrics.get("word_count"):
            print(f"[quality] Word count: {metrics['word_count']}")
        if metrics.get("readability", {}).get("flesch_kincaid_grade"):
            grade = metrics["readability"]["flesch_kincaid_grade"]
            print(f"[quality] Reading level: Grade {grade:.1f}")
        if metrics.get("similarity", {}).get("max_similarity", 0) > 50:
            sim = metrics["similarity"]
            print(f"[quality] Similarity: {sim['max_similarity']:.1f}% to {sim['most_similar_file']}")

        # Calculate and display content score
        score, grade = calculate_content_score(quality_results)
        print(f"[quality] Content score: {score:.1f}/100 (Grade: {grade})")

        if faqs and ("## FAQ" not in body_md and "### FAQ" not in body_md):
            faq_md = ["\n\n## FAQ"]
            for qa in faqs[:5]:
                q = (qa.get("q") or qa.get("question") or "").strip()
                a = (qa.get("a") or qa.get("answer") or "").strip()
                if q and a:
                    faq_md.append(f"\n### {q}\n\n{a}\n")
            body_md += "\n" + "\n".join(faq_md)

        # Use meta_description if available, otherwise use summary
        description = meta_description or summary
        write_post(slug, title, description, body_md)
        used.add(slug)
        generated += 1

        # Mark topic as done immediately (atomic update)
        try:
            mark_topic_done(topic, slug=slug, title=title)
            print(f"[done] Removed from topics.yaml and recorded in topics_done.yaml: {keyword!r}")
        except Exception as e:
            print(f"[warn] Failed to mark topic done for {keyword!r}: {e}", file=sys.stderr)

    if generated == 0:
        msg = "No posts generated this run."
        print(msg)
        if FAIL_ON_EMPTY:
            raise SystemExit(2)

    print(f"Done. Generated {generated} post(s).")

if __name__ == "__main__":
    main()
