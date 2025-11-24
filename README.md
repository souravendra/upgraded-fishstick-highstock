# Highstock Product Lookup

Beauty product enrichment tool that crawls retailers, verifies exact SKU matches, and uses AI for image verification.

## Approach

1. **Crawl** - Search Google Shopping + UPC databases for product data (MSRP, image, description)
2. **Verify** - Rule-based matching ensures exact brand/size/color match (not similar products)
3. **AI** - CLIP model (Transformers.js) verifies product image matches description
4. **Cache** - PostgreSQL stores verified results; cache can be cleared to prove real-time fetch

## Run Locally

```bash
# Backend
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env  # Edit with your DB URL
uvicorn app.main:app --reload

# Image Service (optional)
cd backend/image-service
npm install && node server.js

# Frontend
cd frontend
npm install
echo "VITE_API_URL=http://localhost:8000" > .env
npm run dev
```

## API

```bash
# Health check
curl http://localhost:8000/api/health

# Enrich product
curl -X POST http://localhost:8000/api/enrich \
  -H "Content-Type: application/json" \
  -d '{"name":"No Pressure Lip Liner - #1 - On the Rose","brand_name":"DIBS Beauty","upc":"850029397809"}'

# View cache
curl http://localhost:8000/api/cache

# Clear cache
curl -X DELETE http://localhost:8000/api/cache
```

## Tech Stack

- **Backend**: Python, FastAPI, PostgreSQL, httpx, BeautifulSoup
- **AI**: Transformers.js (CLIP) for image verification
- **Frontend**: React, TypeScript, Vite