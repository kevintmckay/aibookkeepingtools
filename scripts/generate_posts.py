#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Robust generator: writes 1–2 posts/day from topics.yaml

Env:
  OPENAI_API_KEY       (required)
  POSTS_PER_RUN        default "2"
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
REPO_ROOT   = pathlib.Path(__file__).resolve().parent.parent
CONTENT_DIR = REPO_ROOT / "content" / "posts"
TOPICS_FILE = REPO_ROOT / "topics.yaml"

def _int(env_name: str, default: int) -> int:
    try:
        return int(os.getenv(env_name, str(default)))
    except Exception:
        return default

POSTS_PER_RUN       = _int("POSTS_PER_RUN", 2)
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

SYSTEM_EDITOR = (
    "You are a senior technical editor specializing in AI + bookkeeping/accounting. "
    "Write with precision and practical steps. Use Markdown with H2/H3, bullets, short paragraphs. "
    "Cite 3–5 reputable sources inline (official docs, vendor docs, gov, recognized publishers). "
    "Avoid fluff and clickbait. Ensure accuracy."
)

OUTLINE_PROMPT_TMPL = """Create a concise brief and outline for a post.

Topic/Keyword: {keyword}
Audience: {audience}
Search intent: {intent}

Return JSON with keys:
- working_title (<=70 chars, include the main keyword)
- summary (2–3 sentences)
- outline (array of 8–12 section headings)
- entities (10–20 important terms)
- faqs (5 short Q/A pairs)
"""

DRAFT_PROMPT_TMPL = """Write a 1,600–2,100 word article in Markdown.

Working title: {working_title}

Summary:
{summary}

Outline:
{outline_md}

Guidelines:
- Technical depth; step-by-step where applicable.
- Include a short "Quick Start" section.
- Add a "Pitfalls & Gotchas" section.
- Include 3–5 authoritative citations inline as Markdown links.
- Add a 5-item FAQ at the end (use/refine provided Q/A).
- Use H2/H3 headings. Keep paragraphs short. Avoid fluff.

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

def load_topics():
    if not TOPICS_FILE.exists():
        return []
    data = yaml.safe_load(TOPICS_FILE.read_text(encoding="utf-8")) or {}
    return data.get("topics", [])

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
        outline_list = plan.get("outline") or []
        faqs = plan.get("faqs") or []

        base_slug = slugify(title) or slugify(keyword)

        # Skip if a post with this base slug already exists
        if base_slug in used and not ALLOW_DUP_SLUG:
            print(f"[skip] Duplicate slug detected, skipping topic: {keyword!r} -> slug {base_slug!r}")
            continue

        # Optional: allow duplicates with timestamp suffix
        if base_slug in used and ALLOW_DUP_SLUG:
            base_slug = f"{base_slug}-{int(datetime.now(timezone.utc).timestamp())}"

        slug = base_slug
        outline_md = "\n".join(f"- {h}" for h in outline_list) if outline_list else "- Introduction\n- Steps\n- Conclusion"

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
                    max_tokens=2000,   # ~1.5–2k tokens output target
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
                    faq_md.append(f"\n**Q: {q}**\n\n{a}\n")
            body_md += "\n" + "\n".join(faq_md)

        write_post(slug, title, summary, body_md)
        used.add(slug)
        generated += 1

    if generated == 0:
        msg = "No posts generated this run (no heartbeat will be written)."
        print(msg)
        if FAIL_ON_EMPTY:
            # non-zero exit so CI can alert/fail if desired
            raise SystemExit(2)

    print(f"Done. Generated {generated} post(s).")

if __name__ == "__main__":
    main()

