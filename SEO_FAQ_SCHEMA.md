# FAQ Schema Usage

To add FAQ schema to your posts, add an `faq` array to your post's front matter:

```yaml
---
title: "Your Post Title"
description: "Post description"
faq:
  - question: "What is AI bookkeeping?"
    answer: "AI bookkeeping uses artificial intelligence to automate accounting tasks like expense categorization and invoice processing."
  - question: "How much does AI bookkeeping cost?"
    answer: "AI bookkeeping costs vary from $10-50 per month depending on features and business size."
---
```

The FAQ schema will automatically be generated and included in the page's structured data.

## Social Images

- Default social image: `/static/images/default-social.png` (replace with 1200x630 image)
- Per-post images: Add `image: /images/your-post-image.png` to front matter