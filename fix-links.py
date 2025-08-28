#!/usr/bin/env python3
"""
Fix broken internal links in markdown posts.
Replaces placeholder domains with correct relative paths.
"""

import pathlib
import re
import sys
from typing import List, Tuple

# Configuration
CONTENT_DIR = pathlib.Path("content/posts")
BACKUP_SUFFIX = ".backup"

# Pattern to match broken internal links
BROKEN_LINK_PATTERNS = [
    r'\[([^\]]+)\]\(https://yourwebsite\.com(/posts/[^)]+)\)',
    r'\[([^\]]+)\]\(https://aibookkeepingtools\.com(/posts/[^)]+)\)',
    # Add more patterns if needed
]

# Known valid internal post slugs
VALID_SLUGS = {
    'best-ai-bookkeeping-tools-for-small-businesses-2025',
    'how-to-automate-bookkeeping-with-ai-quickbooks-receipt-ocr', 
    'ai-expense-tracking-apps-compared-expensify-vs-zoho-vs-divvy',
    'ai-for-accountants-optimize-workflows-to-serve-more-clients',
    'ai-tax-prep-tools-for-self-employed-in-2025',
    'ai-bookkeeping-software-vs-traditional-accounting-software-2025',
    'comparing-quickbooks-ai-vs-xero-ai-features-for-small-businesses',
    'best-receipt-ocr-apps-for-small-business-in-2025',
    'how-much-does-ai-bookkeeping-software-cost-in-2025',
    'free-ai-bookkeeping-tools-vs-paid-solutions-a-2025-comparison',
    'ai-bookkeeping-roi-calculator-and-cost-savings-analysis-2025',
    'step-by-step-guide-to-implementing-ai-bookkeeping-workflows-2024',
    'integrating-ai-bookkeeping-with-existing-accounting-systems-2024',
    'common-ai-bookkeeping-mistakes-and-how-to-avoid-them-in-2025',
    'ai-bookkeeping-for-e-commerce-businesses-2025-guide'
}

def find_broken_links(content: str) -> List[Tuple[str, str, str]]:
    """Find broken internal links in content.
    
    Returns list of (full_match, anchor_text, relative_path) tuples.
    """
    broken_links = []
    
    for pattern in BROKEN_LINK_PATTERNS:
        matches = re.finditer(pattern, content)
        for match in matches:
            full_match = match.group(0)
            anchor_text = match.group(1)
            relative_path = match.group(2)
            broken_links.append((full_match, anchor_text, relative_path))
    
    return broken_links

def fix_links_in_content(content: str) -> Tuple[str, int]:
    """Fix broken internal links in content.
    
    Returns (fixed_content, num_fixes).
    """
    fixed_content = content
    num_fixes = 0
    
    for pattern in BROKEN_LINK_PATTERNS:
        # Replace broken links with correct relative paths
        def replace_link(match):
            nonlocal num_fixes
            anchor_text = match.group(1)
            relative_path = match.group(2)
            
            # Extract slug from path to validate
            slug_match = re.search(r'/posts/([^/]+)/?', relative_path)
            if slug_match:
                slug = slug_match.group(1)
                if slug in VALID_SLUGS:
                    num_fixes += 1
                    return f'[{anchor_text}]({relative_path})'
                else:
                    print(f"  Warning: Unknown slug '{slug}' - keeping original link")
                    return match.group(0)
            else:
                print(f"  Warning: Could not extract slug from '{relative_path}'")
                return match.group(0)
        
        fixed_content = re.sub(pattern, replace_link, fixed_content)
    
    return fixed_content, num_fixes

def process_file(file_path: pathlib.Path, create_backup: bool = True) -> bool:
    """Process a single markdown file to fix internal links.
    
    Returns True if changes were made.
    """
    if not file_path.exists():
        print(f"File not found: {file_path}")
        return False
    
    print(f"\nProcessing: {file_path.name}")
    
    # Read original content
    try:
        original_content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"  Error reading file: {e}")
        return False
    
    # Find broken links
    broken_links = find_broken_links(original_content)
    if not broken_links:
        print("  No broken links found")
        return False
    
    print(f"  Found {len(broken_links)} broken link(s):")
    for full_match, anchor_text, relative_path in broken_links:
        print(f"    - '{anchor_text}' -> {relative_path}")
    
    # Create backup if requested
    if create_backup:
        backup_path = file_path.with_suffix(file_path.suffix + BACKUP_SUFFIX)
        try:
            backup_path.write_text(original_content, encoding='utf-8')
            print(f"  Backup created: {backup_path.name}")
        except Exception as e:
            print(f"  Warning: Could not create backup: {e}")
    
    # Fix the links
    fixed_content, num_fixes = fix_links_in_content(original_content)
    
    if num_fixes == 0:
        print("  No links were fixed (validation failed)")
        return False
    
    # Write fixed content
    try:
        file_path.write_text(fixed_content, encoding='utf-8')
        print(f"  Fixed {num_fixes} link(s)")
        return True
    except Exception as e:
        print(f"  Error writing fixed content: {e}")
        return False

def get_markdown_files() -> List[pathlib.Path]:
    """Get all markdown files in the content directory."""
    if not CONTENT_DIR.exists():
        print(f"Content directory not found: {CONTENT_DIR}")
        return []
    
    return list(CONTENT_DIR.glob("*.md"))

def main():
    """Main function to fix internal links in all posts."""
    print("Internal Link Fixer")
    print("=" * 30)
    
    # Get all markdown files
    markdown_files = get_markdown_files()
    if not markdown_files:
        print("No markdown files found")
        return
    
    print(f"Found {len(markdown_files)} markdown file(s)")
    
    # Process each file
    files_processed = 0
    files_changed = 0
    
    for file_path in sorted(markdown_files):
        # Skip index file
        if file_path.name.startswith('_'):
            continue
            
        files_processed += 1
        if process_file(file_path, create_backup=True):
            files_changed += 1
    
    print(f"\n" + "=" * 30)
    print(f"Processing complete!")
    print(f"Files processed: {files_processed}")
    print(f"Files changed: {files_changed}")
    
    if files_changed > 0:
        print(f"\nNext steps:")
        print(f"1. Review the changes to make sure they look correct")
        print(f"2. Commit and push the fixed files to trigger deployment")
        print(f"3. Remove backup files with: rm content/posts/*.backup")
    else:
        print("\nNo changes were needed")

if __name__ == "__main__":
    main()
