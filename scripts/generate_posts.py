#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Enhanced robust generator: writes 1 post/day from topics.yaml with SEO optimization and internal linking

Env:
  OPENAI_API_KEY       (required)
  MODEL_OUTLINE        default "gpt-5-mini"
  MODEL_DRAFT          default "gpt-5-mini"
  ALLOW_DUPLICATE_SLUG set "1"/"true" to allow timestamp-suffixed duplicates (default: skip)
  FAIL_ON_EMPTY        set "1"/"true" to exit non-zero if no posts were generated (default: succeed)
"""

import os, re, json, pathlib, time, sys, math
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
import yaml

# --- Paths & config ---
REPO_ROOT       = pathlib.Path(__file__).resolve().parent.parent
CONTENT_DIR     = REPO_ROOT / "content" / "posts"
TOPICS_FILE     = REPO_ROOT / "topics.yaml"
TOPICS_DONE_FILE= REPO_ROOT / "topics_done.yaml"

def _int(env_name: str, default: int) -> int:
    try:
        return int(os.getenv(env_name, str(default)))
    except Exception:
        return default

# Force single post per run - ignore environment variable
POSTS_PER_RUN       = 1
MODEL_OUTLINE_ENV   = os.getenv("MODEL_OUTLINE", "gpt-5-mini")
MODEL_DRAFT_ENV     = os.getenv("MODEL_DRAFT",   "gpt-5-mini")
ALLOW_DUP_SLUG      = os.getenv("ALLOW_DUPLICATE_SLUG", "").strip().lower() in ("1","true","yes")
FAIL_ON_EMPTY       = os.getenv("FAIL_ON_EMPTY", "").strip().lower() in ("1","true","yes")

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

# Enhanced system prompt with internal linking
SYSTEM_EDITOR = (
    "You are a senior technical editor specializing in AI + bookkeeping/accounting. "
    "Write with precision and practical steps. Use Markdown with H2/H3, bullets, short paragraphs. "
    "Include 2-3 internal links to related content where natural and helpful. "
    "Cite 3â€"5 reputable sources inline (official docs, vendor docs, gov, recognized publishers). "
    "Avoid fluff and clickbait. Ensure accuracy. Focus on SEO best practices."
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
- summary (2â€"3 sentences)
- outline (array of 8â€"12 section headings including "Quick Start" section)
- entities (10â€"20 important terms)
- faqs (5 short Q/A pairs)
- internal_link_opportunities (2-3 places where linking to existing content makes sense)
"""

# Enhanced draft prompt with SEO optimization
DRAFT_PROMPT_TMPL = """Write a 1,600â€"2,100 word article in Markdown optimized for SEO and user experience.

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
- Include 3â€"5 authoritative citations inline as Markdown links
- Add a 5-item FAQ at the end (use/refine provided Q/A)
- Use H2/H3 headings. Keep paragraphs short (2-3 sentences max)
- Include at least one comparison table or bulleted pros/cons list
- End with clear next steps or call-to-action

Internal link format: [descriptive anchor text](/posts/slug-here/)

Return ONLY the Markdown body (no front matter, no backticks).
"""

def supports_json_mode(model: str) -> bool:
    return any(model.startswith(p) for p in ("gpt-5", "gpt-4o", "gpt-4.1"))

def _is_modern_model(model: str) -> bool:
    return model.startswith(("gpt-5", "gpt-4o", "gpt-4.1"))

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
            return (resp.choices[0].message.content or "").strip()
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
    description = (description or f"{title} â€" a practical guide.").strip()
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

    models_try = [MODEL_OUTLINE_ENV, "gpt-5-mini", "gpt-4o-mini"]
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
            )
            if txt:
                try:
                    return robust_json(txt)
                except Exception:
                    print(f"Failed plain-parse (model={model}, attempt={attempt+1}); first 200 chars:\n{txt[:200]}", file=sys.stderr)
            backoff_sleep(attempt)

    return None

def main():
    topics = load_topics()
    used = existing_slugs()
    generated = 0

    # Process only the first topic and generate exactly one post
    for topic in (topics or []):
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
        draft_models = [MODEL_DRAFT_ENV, "gpt-5-mini", "gpt-4o-mini"]
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
                    max_tokens=2000,   # ~1.5â€"2k tokens output target
                    timeout=90,
                    json_mode=False,
                    max_retries=5,
                )
                if body_md:
                    break
                backoff_sleep(attempt)
            if body_md:
                break

        if not body_md:
            print(f"Draft failed for: {title}", file=sys.stderr)
            continue

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

        # Exit after generating exactly one post
        break

    if generated == 0:
        msg = "No posts generated this run."
        print(msg)
        if FAIL_ON_EMPTY:
            raise SystemExit(2)

    print(f"Done. Generated {generated} post(s).")

if __name__ == "__main__":
    main()
