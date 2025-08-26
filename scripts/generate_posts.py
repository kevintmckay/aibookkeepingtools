#!/usr/bin/env python3
"""
Generate 1–2 AI posts per run from topics.yaml.
- Reads topics.yaml (root of repo) -> 'topics' list
- Skips posts whose slug already exists in content/posts/
- Writes Markdown with YAML front matter
- Designed for GitHub Actions or local runs

Env vars (optional):
  OPENAI_API_KEY        -> required for API calls
  POSTS_PER_RUN         -> default "2"
  MODEL_OUTLINE         -> default "gpt-5-mini"
  MODEL_DRAFT           -> default "gpt-5"
"""
import os, re, json, pathlib, datetime, textwrap
from typing import List, Dict, Any
import yaml

# ---------- Paths & config ----------
REPO_ROOT   = pathlib.Path(__file__).resolve().parent.parent
CONTENT_DIR = REPO_ROOT / "content" / "posts"
TOPICS_FILE = REPO_ROOT / "topics.yaml"

POSTS_PER_RUN = int(os.getenv("POSTS_PER_RUN", "2"))
MODEL_OUTLINE = os.getenv("MODEL_OUTLINE", "gpt-5-mini")
MODEL_DRAFT   = os.getenv("MODEL_DRAFT",   "gpt-5")

# ---------- OpenAI client ----------
try:
    from openai import OpenAI
except Exception as e:
    raise SystemExit("Missing 'openai' package. Install with: pip install openai pyyaml python-slugify") from e

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise SystemExit("OPENAI_API_KEY not set.")
client = OpenAI(api_key=api_key)

# ---------- Helpers ----------
def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-")[:80]

SYSTEM_EDITOR = (
    "You are a senior technical editor specializing in AI + bookkeeping/accounting. "
    "Write with precision and practicality. Provide concrete steps, examples, and short code/config where helpful. "
    "Use Markdown with H2/H3, bullet lists, and short paragraphs. "
    "Cite 3–5 reputable sources inline (official docs, vendor docs, gov, recognized publishers). "
    "Avoid fluff and clickbait. Ensure accuracy."
)

OUTLINE_PROMPT_TMPL = """Create a concise brief and outline for a post.

Topic/Keyword: {keyword}
Audience: {audience}
Search intent: {intent}

Return JSON with keys:
- working_title (<=70 chars, include the main keyword naturally)
- summary (2–3 sentences on the value delivered)
- outline (array of 8–12 section headings; use H2/H3 style labels)
- entities (10–20 important terms to include naturally for SEO)
- faqs (5 short Q/A pairs)
"""

DRAFT_PROMPT_TMPL = """Write a 1,600–2,100 word article in Markdown based on the approved plan.

Working title: {working_title}

Summary:
{summary}

Outline:
{outline_md}

Guidelines:
- Technical depth; step-by-step where applicable.
- Include a short "Quick Start" section with numbered steps.
- Add a "Pitfalls & Gotchas" section.
- Include 3–5 authoritative citations inline as Markdown links.
- Add a 5-item FAQ at the end (use/refine the provided Q/A).
- Use H2/H3 headings. Keep paragraphs short. Avoid fluff.

Return ONLY the Markdown body (no front matter, no backticks).
"""

def call_openai(model: str, messages: List[Dict[str, str]], max_tokens: int = 3000) -> str:
    """
    Chat Completions:
      - GPT-5 family: use max_completion_tokens; do NOT pass temperature/top_p.
      - Older models (if ever used): fallback to max_tokens + optional temperature.
    """
    kwargs: Dict[str, Any] = {"model": model, "messages": messages}
    if model.startswith("gpt-5"):  # current models reject temperature & max_tokens
        kwargs["max_completion_tokens"] = max_tokens
    else:
        # Back-compat (not expected here)
        kwargs["max_tokens"] = max_tokens
        kwargs["temperature"] = 1.0

    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content

def load_topics() -> List[Dict[str, str]]:
    if not TOPICS_FILE.exists():
        print("No topics.yaml found.")
        return []
    data = yaml.safe_load(TOPICS_FILE.read_text(encoding="utf-8")) or {}
    return data.get("topics", [])

def existing_slugs() -> set:
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    return {p.stem for p in CONTENT_DIR.glob("*.md")}

def to_front_matter(title: str, slug: str, description: str) -> str:
    date = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    # Ensure meta description <= 155 chars
    description = (description or f"{title} — a practical guide.").strip()
    if len(description) > 155:
        description = description[:152].rstrip() + "..."
    fm = {
        "title": title,
        "date": date,
        "slug": slug,
        "description": description,
        "tags": ["AI", "Bookkeeping", "Accounting", "Tools"],
        "categories": ["Guides"],
        "draft": False,
    }
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            joined = ", ".join(json.dumps(x) for x in v)
            lines.append(f"{k}: [{joined}]")
        else:
            lines.append(f"{k}: {json.dumps(v)}")
    lines.append("---")
    return "\n".join(lines)

def robust_json_parse(s: str) -> Dict[str, Any]:
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise

def main():
    topics = load_topics()
    if not topics:
        print("No topics to process.")
        return

    used = existing_slugs()
    generated = 0

    for topic in topics:
        if generated >= POSTS_PER_RUN:
            break

        keyword = (topic.get("keyword") or "").strip()
        if not keyword:
            continue
        audience = (topic.get("audience") or "Small business owners").strip()
        intent   = (topic.get("intent")   or "How-to tutorial").strip()

        # ---- A) Outline ----
        outline_prompt = OUTLINE_PROMPT_TMPL.format(keyword=keyword, audience=audience, intent=intent)
        outline_json = call_openai(
            MODEL_OUTLINE,
            [{"role": "system", "content": SYSTEM_EDITOR},
             {"role": "user", "content": outline_prompt}],
            max_tokens=1200
        )
        try:
            plan = robust_json_parse(outline_json)
        except Exception:
            print("Failed to parse outline JSON; skipping:", keyword)
            continue

        working_title = (plan.get("working_title") or keyword.title()).strip()
        summary = (plan.get("summary") or "").strip()
        outline_list = plan.get("outline") or []
        faqs = plan.get("faqs") or []

        # generate a slug; avoid collisions
        slug = slugify(working_title) or slugify(keyword)
        if not slug:
            slug = slugify(f"post-{datetime.datetime.utcnow().timestamp()}")
        if slug in used:
            alt = slugify(keyword)
            if alt in used:
                print(f"Skipping existing slug: {slug}")
                continue
            slug = alt

        # ---- B) Draft ----
        outline_md = "\n".join(f"- {h}" for h in outline_list) if outline_list else "- Introduction\n- Steps\n- Conclusion"
        draft_prompt = DRAFT_PROMPT_TMPL.format(
            working_title=working_title,
            summary=summary,
            outline_md=outline_md
        )
        body_md = call_openai(
            MODEL_DRAFT,
            [{"role": "system", "content": SYSTEM_EDITOR},
             {"role": "user", "content": draft_prompt}],
            max_tokens=5000
        ).strip()

        # Ensure we include the FAQs at the end if the model didn't
        if faqs and ("## FAQ" not in body_md and "### FAQ" not in body_md):
            faq_md = ["\n\n## FAQ"]
            for qa in faqs[:5]:
                q = (qa.get("q") or qa.get("question") or "").strip()
                a = (qa.get("a") or qa.get("answer") or "").strip()
                if q and a:
                    faq_md.append(f"\n**Q: {q}**\n\n{a}\n")
            body_md += "\n" + "\n".join(faq_md)

        # ---- C) Write file ----
        CONTENT_DIR.mkdir(parents=True, exist_ok=True)
        front = to_front_matter(working_title, slug, summary)
        out_path = CONTENT_DIR / f"{slug}.md"
        out_path.write_text(f"{front}\n\n{body_md}\n", encoding="utf-8")
        print(f"Wrote: {out_path.relative_to(REPO_ROOT)}")

        used.add(slug)
        generated += 1

    print(f"Done. Generated {generated} post(s).")

if __name__ == "__main__":
    main()

