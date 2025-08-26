#!/usr/bin/env python3
import os, re, json, math, time, pathlib, datetime, textwrap, yaml
from slugify import slugify

# -------- Config --------
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTENT_DIR = REPO_ROOT / "content" / "posts"
TOPICS_FILE = REPO_ROOT / "topics.yaml"
POSTS_PER_RUN = int(os.getenv("POSTS_PER_RUN", "2"))

MODEL_OUTLINE = os.getenv("MODEL_OUTLINE", "gpt-5-mini")
MODEL_DRAFT   = os.getenv("MODEL_DRAFT",   "gpt-5")

# -------- OpenAI client --------
try:
    from openai import OpenAI
except Exception:
    raise SystemExit("openai package missing. Action installs it; run 'pip install openai' locally.")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_EDITOR = (
    "You are a senior technical editor specializing in AI + bookkeeping/accounting. "
    "Write with precision. Be practical and specific. Include real steps, examples, "
    "and short code/config where useful. Use Markdown with H2/H3, bullets, and short paragraphs. "
    "Cite 3–5 reputable sources inline (official docs, vendor docs, gov, well-known publishers). "
    "Avoid fluff. No clickbait. Keep claims accurate."
)

OUTLINE_PROMPT_TMPL = """Create a concise brief and outline for a post.

Topic/Keyword: {keyword}
Audience: {audience}
Search intent: {intent}

Return JSON with keys:
- working_title (<=70 chars, compelling, includes the main keyword)
- summary (2-3 sentences of what value the post delivers)
- outline (array of 8–12 H2/H3 section titles)
- entities (10–20 important terms to naturally include for SEO)
- faqs (5 short Q/A pairs to add at the end)
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
- Add a 5-item FAQ at the end (use the provided Q/A; refine if needed).
- Use H2/H3 headings. Keep paragraphs short. No fluff.

Return ONLY the Markdown body (no front matter, no backticks).
"""

def load_topics():
    if not TOPICS_FILE.exists():
        return []
    data = yaml.safe_load(TOPICS_FILE.read_text(encoding="utf-8")) or {}
    return data.get("topics", [])

def existing_slugs():
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    slugs = set()
    for p in CONTENT_DIR.glob("*.md"):
        slugs.add(p.stem)
    return slugs

def call_openai(model, messages, max_tokens=4000, temperature=0.5):
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_completion_tokens=max_tokens
    )
    return resp.choices[0].message.content

def to_front_matter(title, slug, description, tags=None, categories=None, date=None):
    if date is None:
        # Use America/Los_Angeles timestamp (no tz conversion here; GitHub runner is UTC).
        date = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    tags = tags or ["AI", "Bookkeeping", "Accounting", "Tools"]
    categories = categories or ["Guides"]

    # YAML front matter
    fm = {
        "title": title,
        "date": date,
        "slug": slug,
        "description": description[:155],
        "tags": tags,
        "categories": categories,
        "draft": False,
    }
    # Manual YAML to keep dependencies minimal
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(json.dumps(x) for x in v)}]")
        else:
            lines.append(f"{k}: {json.dumps(v)}")
    lines.append("---")
    return "\n".join(lines)

def safe_filename(s):
    s = slugify(s)
    return re.sub(r"[^a-z0-9-]+", "-", s)

def main():
    topics = load_topics()
    if not topics:
        print("No topics found in topics.yaml")
        return

    done = 0
    used_slugs = existing_slugs()

    for topic in topics:
        if done >= POSTS_PER_RUN:
            break

        keyword = topic.get("keyword", "").strip()
        if not keyword:
            continue
        audience = topic.get("audience", "Small business owners")
        intent   = topic.get("intent", "How-to tutorial")

        # 1) Outline
        outline_prompt = OUTLINE_PROMPT_TMPL.format(
            keyword=keyword, audience=audience, intent=intent
        )
        outline_json = call_openai(
            MODEL_OUTLINE,
            [
                {"role": "system", "content": SYSTEM_EDITOR},
                {"role": "user", "content": outline_prompt},
            ],
            max_tokens=1200,
            temperature=0.4,
        )

        # Parse JSON-ish output robustly
        try:
            plan = json.loads(outline_json)
        except Exception:
            # Try to extract JSON block
            m = re.search(r"\{.*\}", outline_json, flags=re.S)
            if not m:
                print("Failed to parse outline JSON; skipping topic:", keyword)
                continue
            plan = json.loads(m.group(0))

        working_title = plan.get("working_title") or keyword.title()
        summary = plan.get("summary", "")
        outline = plan.get("outline", [])
        entities = plan.get("entities", [])
        faqs = plan.get("faqs", [])

        # Generate a slug; skip if already exists
        slug = safe_filename(working_title)[:80].strip("-")
        if slug in used_slugs:
            # try keyword-based slug
            alt = safe_filename(keyword)[:80].strip("-")
            if alt in used_slugs:
                print(f"Skipping (slug exists): {slug}")
                continue
            slug = alt

        # 2) Draft
        outline_md = "\n".join(f"- {h}" for h in outline) if outline else "- Introduction\n- Steps\n- Conclusion"
        draft_prompt = DRAFT_PROMPT_TMPL.format(
            working_title=working_title,
            summary=summary,
            outline_md=outline_md,
        )
        body_md = call_openai(
            MODEL_DRAFT,
            [
                {"role": "system", "content": SYSTEM_EDITOR},
                {"role": "user", "content": draft_prompt},
            ],
            max_tokens=5000,
            temperature=0.5,
        )

        # 3) Front matter + write file
        description = summary if summary else f"{working_title} — a practical guide."
        fm = to_front_matter(
            title=working_title,
            slug=slug,
            description=description,
            tags=["AI", "Bookkeeping", "Accounting", "Tools"],
            categories=["Guides"]
        )

        CONTENT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = CONTENT_DIR / f"{slug}.md"
        post_md = f"{fm}\n\n{body_md.strip()}\n"
        out_path.write_text(post_md, encoding="utf-8")

        print(f"Wrote post: {out_path}")
        used_slugs.add(slug)
        done += 1

    print(f"Done. Generated {done} post(s).")

if __name__ == "__main__":
    main()

