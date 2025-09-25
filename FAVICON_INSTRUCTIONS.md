# Favicon Generation Instructions

## Current Status
- ✅ Created `favicon.svg` - modern browsers support this
- ⚠️ Need `favicon.ico` for older browser compatibility

## Quick Option: Use Online Converter
1. Go to https://favicon.io/favicon-converter/
2. Upload the `static/favicon.svg` file
3. Download the generated favicon package
4. Replace `static/favicon.ico` with the downloaded ICO file

## Alternative: Use RealFaviconGenerator
1. Visit https://realfavicongenerator.net/
2. Upload `static/favicon.svg`
3. Generate all favicon formats
4. Download and extract to `static/` folder

## Manual Creation
If you have design software:
1. Create a 32x32 pixel square image
2. Use blue background (#2563eb)
3. Add white calculator/AI icon
4. Export as ICO format

## Current favicon.svg features:
- Blue circular background
- Calculator-like grid (representing bookkeeping)
- "AI" text at top
- 32x32 viewBox, scales well