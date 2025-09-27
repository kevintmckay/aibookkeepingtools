# Batch Validation Checklist - Enhanced Posts

## Pre-Batch Validation

### ✅ **Before Running Enhancement:**
- [ ] Check script is working: `python3 scripts/enhance_existing_posts.py --list | head -5`
- [ ] Verify git status is clean: `git status`
- [ ] Confirm target batch size: **3 posts**
- [ ] Note starting post count: `find content/posts -name "*_enhanced.md" | wc -l`

---

## Post-Enhancement Validation

### ✅ **Technical Validation (Each Enhanced Post):**

#### 1. File Structure Check
- [ ] **Enhanced file created**: `content/posts/[name]_enhanced.md` exists
- [ ] **No script errors**: Enhancement completed without timeout/failure
- [ ] **Word count improved**: Enhanced > Original (target 1600+ words)

#### 2. Content Quality Verification (Sample 1 post per batch)
```bash
# Check sample post structure
head -30 content/posts/[sample-post]_enhanced.md
```

**Verify:**
- [ ] **Clean frontmatter**: Single YAML block, no duplicates
- [ ] **No markdown artifacts**: No ```markdown blocks or duplicate headers
- [ ] **Proper formatting**: Clean headings, lists, tables
- [ ] **Real examples**: Company names, not "XYZ Corp" or "Company A"
- [ ] **Current data**: Statistics with 2024-2025 dates
- [ ] **Internal links preserved**: `/posts/` links present and unchanged

#### 3. SEO Metadata Preservation
```bash
# Extract frontmatter from enhanced post
sed -n '1,/^---$/p' content/posts/[sample-post]_enhanced.md
```

**Verify preserved:**
- [ ] **Title**: Identical to original
- [ ] **Slug**: Identical to original (URL safety)
- [ ] **Description**: Identical to original (meta tag safety)
- [ ] **Tags**: Same array as original
- [ ] **Categories**: Same as original
- [ ] **Date**: Same publication date

---

## Batch Replacement Validation

### ✅ **Before Replacement:**
- [ ] **All 3 enhancements successful**: No failures in batch
- [ ] **Sample quality check passed**: 1 post manually reviewed
- [ ] **Backup available**: Git status shows staged changes

### ✅ **After Replacement:**
```bash
# Replace enhanced with originals
for file in content/posts/*_enhanced.md; do
    original="${file/_enhanced.md/.md}"
    echo "Replacing: $original"
    mv "$file" "$original"
done
```

**Verify:**
- [ ] **Files replaced successfully**: No `_enhanced.md` files remain
- [ ] **Git shows modifications**: `git status` shows 3 modified files
- [ ] **No errors in replacement**: All mv commands succeeded

---

## Content Quality Spot Check

### ✅ **Enhanced Content Validation (1 Random Post):**

#### Word Count Verification
```bash
# Check word count improvement
wc -w content/posts/[sample-post].md
# Target: 1600+ words
```

#### Quality Indicators Check
```bash
# Search for quality improvements
grep -i "case study\|real.world\|example\|statistic\|2024\|2025" content/posts/[sample-post].md
```

**Verify present:**
- [ ] **Real company names**: Specific businesses mentioned
- [ ] **Current statistics**: 2024-2025 data with sources
- [ ] **Case studies**: Concrete examples with metrics
- [ ] **Implementation guides**: Step-by-step instructions
- [ ] **Pricing tables**: Current, verified pricing data

#### Internal Linking Check
```bash
# Verify internal links preserved
grep -o '/posts/[^)]*' content/posts/[sample-post].md
```

**Verify:**
- [ ] **Links preserved**: Same internal links as original
- [ ] **No broken references**: All `/posts/` links valid
- [ ] **Additional links added**: New relevant internal links

---

## Final Batch Validation

### ✅ **Git & Deployment Safety:**
```bash
# Verify git status
git status
git diff --stat
```

**Verify:**
- [ ] **3 files modified**: Exactly 3 posts changed
- [ ] **No deletions**: No files accidentally deleted
- [ ] **Clean diff**: Only content improvements, no structural changes

### ✅ **Site Structure Safety:**
- [ ] **URLs unchanged**: Slugs identical = no broken links
- [ ] **Navigation intact**: All internal references preserved
- [ ] **SEO safe**: Meta tags and structure unchanged

---

## Batch Completion Checklist

### ✅ **Commit Preparation:**
- [ ] **Quality confirmed**: Spot check passed
- [ ] **Safety verified**: No SEO/structural issues
- [ ] **Git ready**: Changes staged and verified

### ✅ **Progress Tracking:**
- [ ] **Batch completed**: 3 posts enhanced and replaced
- [ ] **Total progress**: Update remaining count
- [ ] **Next batch ready**: Can proceed safely

---

## Quick Reference Commands

```bash
# Run enhancement batch
python3 scripts/enhance_existing_posts.py --batch 3

# Check enhanced files
find content/posts -name "*_enhanced.md"

# Spot check quality (replace FILENAME)
head -50 content/posts/FILENAME_enhanced.md

# Replace originals
for file in content/posts/*_enhanced.md; do
    mv "$file" "${file/_enhanced.md/.md}"
done

# Verify git status
git status && git diff --stat
```

---

## 🚨 **Stop Conditions - Don't Proceed If:**
- [ ] Any enhancement fails/times out
- [ ] Enhanced post has formatting issues
- [ ] SEO metadata is altered
- [ ] Internal links are broken
- [ ] Git shows unexpected changes

---

**✅ All checks passed = Safe to commit and proceed to next batch**