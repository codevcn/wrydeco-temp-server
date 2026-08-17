WRYDECO VNOTE -> SHOPIFY CONTENT > FILES FLOW

Files:
- flow_vnote.py
- migrate_vnote_description_images.py
- split_shopify_products.py
- flow_vnote.cmd
- migrate_vnote_description_images.cmd
- split_shopify_products.cmd
- .upload.env.example

Target rule:
- ONLY replace URL in the src attribute of <img> tags.
- The parsed hostname must be exactly: vnote.io.vn
- Other domains are skipped.
- Subdomains such as cdn.vnote.io.vn are skipped.
- vnote.io.vn in href, text, data-src, srcset, etc. is skipped.

Flow:
1. Count unique Shopify products by Handle.
2. If products > MAX_PRODUCTS_CSV_NUMBER (default 50), split into parts of max 50 products.
3. For each CSV, find only <img src> whose hostname is exactly vnote.io.vn.
4. Download source image.
5. Upload to Shopify Content > Files through stagedUploadsCreate -> staged binary upload -> fileCreate.
6. Wait until image READY and get cdn.shopify.com URL.
7. Replace only the matched img src.
8. Validate:
   - Amazon Link metafield unchanged 100%.
   - No target vnote.io.vn img src remains.
   - Every non-target img src remains unchanged.
   - Replacement URLs are Shopify CDN URLs.

Output names:
- No split: <input>_vnote_shopify_files.csv
- Split: <input>_part_N_vnote_shopify_files.csv

Shared cache:
- <input>_vnote_shopify_upload_cache.json

Use the same .upload.env format as the Amazon flow:
STORE_UPLOAD_DOMAIN=your-store.myshopify.com
STORE_UPLOAD_CLIENT_ID=...
STORE_UPLOAD_CLIENT_SECRET=...
STORE_UPLOAD_ACCESS_TOKEN=...

Run:
flow_vnote.cmd
