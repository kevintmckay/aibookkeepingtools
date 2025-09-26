# Post Enhancement Workflow

## Overview
The `enhance_existing_posts.py` script upgrades existing blog posts to premium 2025 quality standards using the o3 model.

## Quick Start

### 1. List posts needing enhancement:
```bash
python3 scripts/enhance_existing_posts.py --list
```

### 2. Enhance a single post:
```bash
python3 scripts/enhance_existing_posts.py --post content/posts/example.md
```

### 3. Process a batch (recommended: 3-5 posts at a time):
```bash
python3 scripts/enhance_existing_posts.py --batch 3
```

## Enhancement Quality Standards

The script enhances posts to include:
- ✅ **1,600+ words** (target 1,800-2,200)
- ✅ **Real company examples** (no "XYZ Corp")
- ✅ **Current statistics** with 2024-2025 dates
- ✅ **Detailed case studies** with metrics
- ✅ **Pricing tables** with verified current data
- ✅ **Comprehensive sections** (Best Practices, Implementation Guide, etc.)

## Batch Processing Recommendations

### Daily Workflow:
```bash
# Morning: Process 3 posts
python3 scripts/enhance_existing_posts.py --batch 3

# Review enhanced posts manually
# Replace originals if quality is good
```

### Time Estimates:
- **Single post enhancement**: 3-5 minutes
- **Batch of 5 posts**: 15-25 minutes
- **Manual review per post**: 5-10 minutes

### Cost Management:
- Current budget: $100/day for enhancements
- Estimated cost per post: $0.60-1.20
- Daily capacity: ~80-150 posts (if needed)

## File Management

Enhanced posts are saved with `_enhanced.md` suffix:
- Original: `content/posts/example.md`
- Enhanced: `content/posts/example_enhanced.md`

After review, replace the original:
```bash
mv content/posts/example_enhanced.md content/posts/example.md
```

## Quality Control

Review each enhanced post for:
1. **Accuracy** of statistics and pricing
2. **Relevance** of company examples
3. **Flow** and readability
4. **Internal links** preserved
5. **SEO** optimization maintained

## Progress Tracking

Total posts needing enhancement: **81**

Recommended schedule:
- **Week 1-2**: 5 posts/day = 35 posts
- **Week 3-4**: 5 posts/day = 35 posts
- **Week 5**: 11 remaining posts

Complete upgrade in **5 weeks** with daily 15-25 minute sessions.