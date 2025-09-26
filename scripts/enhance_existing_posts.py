#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Post Enhancement Script: Upgrade existing posts to premium quality standards

This script enhances existing blog posts using the o3 model to:
- Expand content to 1600+ words
- Add real company examples and case studies
- Include specific statistics with dates
- Add comprehensive sections and depth
- Include pricing tables and real data

Usage:
  python scripts/enhance_existing_posts.py --post content/posts/example.md
  python scripts/enhance_existing_posts.py --batch 5  # Process 5 posts
  python scripts/enhance_existing_posts.py --list     # Show posts needing enhancement
"""

import os
import sys
import argparse
import pathlib
import re
from datetime import datetime
from typing import List, Optional, Dict, Any
import yaml

# OpenAI client setup
try:
    import openai
except ImportError:
    print("Error: openai package not installed. Run: pip install openai")
    sys.exit(1)

# Load environment variables from .env file if it exists
def load_env_file():
    env_file = pathlib.Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    if key.strip() and not os.getenv(key.strip()):
                        os.environ[key.strip()] = value.strip()

def _str(key: str, default: str = "") -> str:
    return os.getenv(key, default)

def _int(key: str, default: int = 0) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default

# Load environment
load_env_file()

# Initialize OpenAI client
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def chat_with_retry(model: str, messages: list, max_tokens: int = 4000, timeout: int = 120,
                   json_mode: bool = False, max_retries: int = 3, operation: str = "chat") -> str:
    """Simple chat function with retry logic."""
    for attempt in range(1, max_retries + 1):
        try:
            # Prepare request parameters
            params = {
                "model": model,
                "messages": messages,
                "timeout": timeout,
            }

            # Use correct token parameter based on model
            if model.startswith("o3") or model.startswith("o1"):
                params["max_completion_tokens"] = max_tokens
            else:
                params["max_tokens"] = max_tokens

            if json_mode:
                params["response_format"] = {"type": "json_object"}

            response = client.chat.completions.create(**params)
            return response.choices[0].message.content
        except Exception as e:
            if attempt >= max_retries:
                print(f"[{operation}] {model} error: {e} (giving up)")
                return ""
            print(f"[{operation}] {model} error: {e} (attempt {attempt}/{max_retries})")
            import time
            time.sleep(2 ** attempt)  # Exponential backoff
    return ""

# Configuration
MODEL_ENHANCE = _str("MODEL_ENHANCE", "o3")  # Use o3 for premium quality
MAX_ENHANCE_COST_USD = _int("MAX_ENHANCE_COST_USD", 100)  # Daily budget for enhancements
MIN_WORD_COUNT_TARGET = _int("MIN_WORD_COUNT_TARGET", 1600)  # Target word count

# Enhanced system prompt for post improvement
ENHANCEMENT_SYSTEM_PROMPT = (
    "You are a senior content editor specializing in upgrading existing blog posts to premium 2025 quality standards. "
    "Your task is to significantly enhance and expand existing content while preserving the original intent and structure. "
    "Focus on making content more authoritative, comprehensive, and valuable to readers. "
    "REQUIREMENTS: "
    "- Expand to minimum 1600 words (target 1800-2200 words) "
    "- Add realistic company examples (avoid 'XYZ Corp' - use real company names) "
    "- Include specific statistics with exact dates (prefer 2024-2025 data) "
    "- Add detailed case studies with concrete metrics and outcomes "
    "- Include pricing tables with real current pricing from official sources "
    "- Add comprehensive sections like 'Common Challenges', 'Best Practices', 'Implementation Guide' "
    "- Enhance existing sections with more depth, examples, and practical advice "
    "- Maintain SEO optimization and internal linking structure "
    "- Ensure professional, authoritative tone throughout "
    "- Add actionable insights and specific recommendations "
    "AUTHENTICITY: Use real companies, actual pricing, verifiable statistics, and concrete examples. "
    "DEPTH: Every section should be substantially expanded with practical details, step-by-step guidance, and real-world context."
)

ENHANCEMENT_PROMPT_TEMPLATE = """TASK: Enhance this existing blog post to premium 2025 quality standards.

ORIGINAL POST:
{original_content}

ENHANCEMENT REQUIREMENTS:
- Target word count: {target_words}+ words (current: {current_words} words)
- Add {words_needed}+ words of premium content
- Replace generic examples with real company names and specific scenarios
- Add detailed case studies with actual metrics and outcomes
- Include pricing tables with real current pricing (verify with official sources)
- Add comprehensive new sections for depth and value
- Enhance all existing sections with more detail, examples, and practical advice
- Include specific statistics with publication dates (prefer 2024-2025)
- Add step-by-step implementation guides where relevant
- Maintain all existing internal links and SEO optimization

CONTENT EXPANSION AREAS:
1. Add "Quick Start Guide" section with detailed steps
2. Include "Common Challenges & Solutions" with specific examples
3. Add "Best Practices" section with actionable recommendations
4. Include comparison tables with real tools and current pricing
5. Add case studies with specific company names and measurable results
6. Expand FAQ section with comprehensive answers
7. Add "Implementation Timeline" or "Getting Started" roadmap
8. Include "Advanced Tips" or "Pro Strategies" section

OUTPUT: Return ONLY the enhanced blog post content (body text) in markdown format. Do NOT include frontmatter, YAML headers, or markdown code blocks. Start directly with the enhanced content. The original frontmatter will be preserved automatically.
"""

def extract_frontmatter_and_content(post_path: str) -> tuple[Dict[str, Any], str]:
    """Extract YAML frontmatter and content from a markdown file."""
    with open(post_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split frontmatter and content
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            frontmatter = yaml.safe_load(parts[1])
            body_content = parts[2].strip()
            return frontmatter, body_content

    # No frontmatter found
    return {}, content

def count_words(text: str) -> int:
    """Count words in text content."""
    # Remove markdown syntax for more accurate word count
    clean_text = re.sub(r'[#*`\[\]()_]', '', text)
    clean_text = re.sub(r'\s+', ' ', clean_text)
    return len(clean_text.split())

def needs_enhancement(post_path: str, min_words: int = 1400) -> bool:
    """Check if a post needs enhancement based on word count and quality indicators."""
    try:
        frontmatter, content = extract_frontmatter_and_content(post_path)
        word_count = count_words(content)

        # Check word count
        if word_count < min_words:
            return True

        # Check for quality indicators (generic examples, lack of case studies)
        quality_indicators = [
            'XYZ Corp' in content,
            'Company A' in content,
            'Tool X' in content,
            content.count('case study') == 0,
            content.count('Case Study') == 0,
            '2023' in content and '2024' not in content,  # Outdated data
        ]

        # If multiple quality issues, needs enhancement
        return sum(quality_indicators) >= 2

    except Exception as e:
        print(f"Error checking {post_path}: {e}")
        return False

def enhance_post_content(original_content: str, target_words: int = 1600) -> Optional[str]:
    """Enhance a single post using the o3 model."""
    current_words = count_words(original_content)
    words_needed = max(target_words - current_words, 400)  # At least 400 word expansion

    prompt = ENHANCEMENT_PROMPT_TEMPLATE.format(
        original_content=original_content,
        target_words=target_words,
        current_words=current_words,
        words_needed=words_needed
    )

    print(f"Enhancing post: {current_words} → {target_words}+ words")

    # Use o3 model for premium enhancement
    enhanced_content = chat_with_retry(
        model=MODEL_ENHANCE,
        messages=[
            {"role": "system", "content": ENHANCEMENT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        max_tokens=8000,  # Large token limit for comprehensive enhancements
        timeout=300,      # 5 minute timeout for complex enhancements
        json_mode=False,
        max_retries=3,
        operation="enhancement"
    )

    return enhanced_content

def enhance_single_post(post_path: str, output_path: Optional[str] = None) -> bool:
    """Enhance a single blog post."""
    try:
        print(f"\n📝 Enhancing: {post_path}")

        # Extract original content
        frontmatter, original_content = extract_frontmatter_and_content(post_path)
        original_words = count_words(original_content)

        print(f"Original word count: {original_words}")

        # Enhance the content
        enhanced_content = enhance_post_content(original_content, MIN_WORD_COUNT_TARGET)

        if not enhanced_content:
            print("❌ Enhancement failed")
            return False

        # Count enhanced words
        enhanced_words = count_words(enhanced_content)
        print(f"Enhanced word count: {enhanced_words} (+{enhanced_words - original_words})")

        # Prepare output
        if output_path is None:
            output_path = post_path.replace('.md', '_enhanced.md')

        # Clean enhanced content - remove any duplicate frontmatter
        enhanced_content = enhanced_content.strip()

        # Remove markdown code blocks and duplicate frontmatter from enhanced content
        if enhanced_content.startswith('```markdown'):
            # Find the end of the code block and extract just the content
            lines = enhanced_content.split('\n')
            content_start = 0
            in_frontmatter = False

            for i, line in enumerate(lines):
                if line.strip() == '```markdown':
                    continue
                elif line.strip() == '---' and not in_frontmatter:
                    in_frontmatter = True
                    continue
                elif line.strip() == '---' and in_frontmatter:
                    in_frontmatter = False
                    content_start = i + 1
                    break
                elif line.strip() == '```':
                    content_start = i + 1
                    break

            if content_start > 0:
                enhanced_content = '\n'.join(lines[content_start:]).strip()

        # Write enhanced post with original frontmatter
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('---\n')
            yaml.dump(frontmatter, f, default_flow_style=False)
            f.write('---\n\n')
            f.write(enhanced_content)

        print(f"✅ Enhanced post saved to: {output_path}")
        print(f"Quality improvement: {original_words} → {enhanced_words} words")

        return True

    except Exception as e:
        print(f"❌ Error enhancing {post_path}: {e}")
        return False

def list_posts_needing_enhancement(content_dir: str = "content/posts") -> List[str]:
    """List all posts that need enhancement."""
    posts_needing_enhancement = []

    for post_path in pathlib.Path(content_dir).glob("*.md"):
        if post_path.name == "_index.md":
            continue

        if needs_enhancement(str(post_path)):
            posts_needing_enhancement.append(str(post_path))

    return sorted(posts_needing_enhancement)

def process_batch(batch_size: int = 5, content_dir: str = "content/posts") -> None:
    """Process a batch of posts for enhancement."""
    posts_to_enhance = list_posts_needing_enhancement(content_dir)

    if not posts_to_enhance:
        print("✅ No posts need enhancement!")
        return

    print(f"📊 Found {len(posts_to_enhance)} posts needing enhancement")
    print(f"🚀 Processing batch of {min(batch_size, len(posts_to_enhance))} posts")

    successful = 0
    for i, post_path in enumerate(posts_to_enhance[:batch_size]):
        print(f"\n--- Processing {i+1}/{min(batch_size, len(posts_to_enhance))} ---")

        if enhance_single_post(post_path):
            successful += 1

        # Small delay between posts
        import time
        time.sleep(2)

    print(f"\n📈 Batch complete: {successful}/{min(batch_size, len(posts_to_enhance))} posts enhanced")

    remaining = len(posts_to_enhance) - batch_size
    if remaining > 0:
        print(f"📋 {remaining} posts remaining for future batches")

def main():
    """Main function to handle command line arguments."""
    parser = argparse.ArgumentParser(description="Enhance existing blog posts to premium quality")
    parser.add_argument("--post", help="Path to specific post to enhance")
    parser.add_argument("--batch", type=int, help="Process a batch of N posts")
    parser.add_argument("--list", action="store_true", help="List posts needing enhancement")
    parser.add_argument("--output", help="Output path for enhanced post")
    parser.add_argument("--content-dir", default="content/posts", help="Content directory path")

    args = parser.parse_args()

    if args.list:
        posts = list_posts_needing_enhancement(args.content_dir)
        print(f"📋 Found {len(posts)} posts needing enhancement:")
        for post in posts:
            frontmatter, content = extract_frontmatter_and_content(post)
            words = count_words(content)
            print(f"  - {post} ({words} words)")

    elif args.post:
        enhance_single_post(args.post, args.output)

    elif args.batch:
        process_batch(args.batch, args.content_dir)

    else:
        parser.print_help()

if __name__ == "__main__":
    main()