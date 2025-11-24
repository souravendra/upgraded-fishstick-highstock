"""
Main FastAPI application.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, create_tables
from app.schemas import ProductInput, ProductOutput, ErrorResponse
from app.service import EnrichmentService


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle startup and shutdown events."""
    # Startup
    print("Creating database tables...")
    await create_tables()
    print("✅ Database ready")

    # Check if image service is available
    from app.image_client import image_client

    if await image_client.is_available():
        print(f"✅ Image verification service connected ({image_client.base_url})")
        print("   Pre-loading AI models...")
        await image_client.preload_models()
        print("✅ AI models ready")
    else:
        print("⚠️  Image verification service not available")
        print(f"   Expected at: {image_client.base_url}")
        print("   Run: cd image-service && npm start")
        print("   (Image verification will be skipped)")

    print("\n🚀 Server started successfully\n")

    yield

    # Shutdown
    print("Server shutting down...")
    await image_client.close()

    from app.image_fetcher import image_fetcher

    await image_fetcher.close()

    from app.msrp_lookup import msrp_lookup

    await msrp_lookup.close()


# Create FastAPI app
app = FastAPI(
    title="Highstock Product Enrichment API",
    description="Beauty product lookup tool with web crawling",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global service instance
enrichment_service = EnrichmentService()


@app.get("/")
async def root() -> dict:
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Highstock Product Enrichment API",
        "version": "1.0.0",
    }


@app.post(
    "/api/enrich",
    response_model=ProductOutput,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def enrich_product(
    product: ProductInput, db: AsyncSession = Depends(get_db)
) -> ProductOutput:
    """
    Enrich product data by UPC.

    Flow:
    1. Check database for cached data
    2. If not found, crawl retailers (Sephora, Ulta, etc.)
    3. Aggregate results and calculate confidence
    4. Save to database if confidence >= 90%
    5. Return enriched data

    Args:
        product: Product input data (name, brand, UPC, size, color)
        db: Database session (injected)

    Returns:
        ProductOutput: Enriched product data with confidence score

    Raises:
        HTTPException: If enrichment fails
    """
    try:
        result = await enrichment_service.enrich_product(product, db)
        return result

    except Exception as e:
        print(f"[ERROR] Enrichment failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to enrich product: {str(e)}"
        )


@app.get("/api/health")
async def health_check() -> dict:
    """Detailed health check."""
    return {"status": "healthy", "database": "connected", "crawlers": "ready"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG
    )
