mkdir -p scripts
cat > scripts/generate_posts.py <<'PY'
#!/usr/bin/env python3
import os, re, json, pathlib, datetime, yaml
from typing import List, Dict, Any

REPO_ROOT   = pathlib.Path(__file__).resolve().parent.parent
CONTENT_DIR = REPO_ROOT / "content" / "posts"
TOPICS_FILE = REPO_ROOT / "topics.yaml"

POSTS_PER_RUN = int(os.getenv("POSTS_PER_RUN", "2"))
MODEL_OUTLINE = os.getenv("MODEL_OUTLINE", "gpt-5-mini")
MODEL_DRAFT   = os.getenv("MODEL_DRAFT",   "gpt-5")

# --- OpenAI client ---
try:
    from openai import OpenAI
except Exception as e:
    raise SystemExit("Missing 'openai' package. In CI it installs automatically. Locally: pip install openai pyyaml") from e

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise SystemExit("OPENAI_API_KEY not set.")
client = OpenAI(api_key=api_key)

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-")[:80]

SYSTEM_EDITOR = (
    "You are a senior technical editor specializing in AI + bookkeeping/accounting. "
    "Write with precision and practical steps. Use Markdown with H2/H3, bullets, short paragraphs. "
    "Cite 3–5 reputable sources inline. Avoid fluff and clickbait. Ensure accuracy."
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
- Add a 5-item FAQ at the end.
- Use H2/H3 headings. Keep paragraphs short. Avoid fluff.

Return ONLY the Markdown body (no front matter, no backticks).
"""

def call_openai(model: str, messages: List[Dict[str, str]], max_tokens: int = 3000) -> str:
    kwargs: Dict[str, Any] = {"model": model, "messages": messages}
    if model.startswith("gpt-5"):
        kwargs["max_completion_tokens"] = max_tokens  # new param for GPT-5 family
    else:
        kwargs["max_tokens"] = max_tokens
        kwargs["temperature"] = 1.0
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content

def load_topics():
    if not TOPICS_FILE.exists():
        return []
    data = yaml.safe_load(TOPICS_FILE.read_text(encoding="utf-8")) or {}
    return data.get("topics", [])

def existing_slugs():
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    return {p.stem for p in CONTENT_DIR.glob("*.md")}

def now_past_iso():
    return (datetime.datetime.utcnow() - datetime.timedelta(minutes=5)).isoformat(timespec="seconds") + "Z"

def front_matter(title, slug, description):
    description = (description or f"{title} — a practical guide.").strip()
    if len(description) > 155:
        description = description[:152].rstrip() + "..."
    fm = {
        "title": title,
        "date": now_past_iso(),  # 5 minutes in the past
        "slug": slug,
        "description": description,
        "tags": ["AI", "Bookkeeping", "Accounting", "Tools"],
        "categories": ["Guides"],
        "draft": False,
    }
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(json.dumps(x) for x in v)}]")
        else:
            lines.append(f"{k}: {json.dumps(v)}")
    lines.append("---")
    return "\n".join(lines)

def robust_json(s: str) -> Dict[str, Any]:
    try:
        return json.loads(s)
    except Exception:
        import re
        m = re.search(r"\{.*\}", s, flags=re.S)
        if not m:
            raise
        return json.loads(m.group(0))

def write_post(slug: str, title: str, description: str, body_md: str):
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    out = CONTENT_DIR / f"{slug}.md"
    out.write_text(front_matter(title, slug, description) + "\n\n" + body_md.strip() + "\n", encoding="utf-8")
    print(f"Wrote: {out.relative_to(REPO_ROOT)}")

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

        # A) Outline
        try:
            outline_json = call_openai(
                MODEL_OUTLINE,
                [{"role": "system", "content": SYSTEM_EDITOR},
                 {"role": "user", "content": OUTLINE_PROMPT_TMPL.format(keyword=keyword, audience=audience, intent=intent)}],
                max_tokens=1200
            )
            plan = robust_json(outline_json)
        except Exception as e:
            print("Outline generation failed:", repr(e))
            continue

        title   = (plan.get("working_title") or keyword.title()).strip()
        summary = (plan.get("summary") or "").strip()
        outline_list = plan.get("outline") or []
        faqs = plan.get("faqs") or []

        base_slug = slugify(title) or slugify(keyword) or f"post-{int(datetime.datetime.utcnow().timestamp())}"
        slug = base_slug if base_slug not in used else f"{base_slug}-{int(datetime.datetime.utcnow().timestamp())}"

        # B) Draft
        outline_md = "\n".join(f"- {h}" for h in outline_list) if outline_list else "- Introduction\n- Steps\n- Conclusion"
        try:
            body_md = call_openai(
                MODEL_DRAFT,
                [{"role": "system", "content": SYSTEM_EDITOR},
                 {"role": "user", "content": DRAFT_PROMPT_TMPL.format(working_title=title, summary=summary, outline_md=outline_md)}],
                max_tokens=5000
            ).strip()
        except Exception as e:
            print("Draft generation failed:", repr(e))
            continue

        # Ensure FAQ presence
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

    # Fallback: write a heartbeat post if nothing was generated (helps diagnose CI)
    if generated == 0:
        slug = f"heartbeat-{int(datetime.datetime.utcnow().timestamp())}"
        title = "Publishing Heartbeat"
        desc = "This placeholder verifies the daily workflow and file writes."
        body = "If you see this, the generator didn't create a topic-based article this run."
        write_post(slug, title, desc, body)

    print(f"Done. Generated {generated} post(s).")

if __name__ == "__main__":
    main()
PY

chmod +x scripts/generate_posts.py
git add scripts/generate_posts.py
git commit -m "chore(generator): hardened — always writes, past-dated, auto-suffix slugs, clear logs"
git push

