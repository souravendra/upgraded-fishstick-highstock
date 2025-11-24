"""
Product enrichment service.
"""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EnrichedProduct
from app.schemas import (
    ProductInput,
    ProductOutput,
    CrawlSource,
    VerificationInfo,
    ImageVerificationInfo,
)
from app.crawlers.manager import CrawlerManager, aggregate_crawl_results
from app.image_client import image_client


class EnrichmentService:
    """Service for enriching product data."""

    def __init__(self) -> None:
        self.crawler_manager = CrawlerManager()

    async def enrich_product(
        self, product_input: ProductInput, db: AsyncSession
    ) -> ProductOutput:
        """
        Main enrichment flow:
        1. Check database for existing data
        2. If not found, crawl retailers
        3. Aggregate results WITH VERIFICATION
        4. Verify image using AI (Transformers.js/CLIP)
        5. Save to database (if confidence >= 85% AND verified)
        6. Return enriched data
        """

        # Step 1: Check database
        existing = await self._get_from_db(product_input.upc, db)
        if existing:
            print(f"[DB] Cache hit for UPC {product_input.upc}")
            return self._db_to_output(existing)

        print(f"[DB] Cache miss for UPC {product_input.upc}, crawling...")

        # Step 2: Crawl retailers (with fallback to brand+name search)
        crawl_results = await self.crawler_manager.search_all(
            upc=product_input.upc,
            brand=product_input.brand_name,
            product_name=product_input.name,
        )

        # Step 3: Aggregate results WITH VERIFICATION
        # This is critical - we verify brand, size, and color match exactly

        # Normalize "null" strings to None (frontend may send "null" as string)
        input_size = (
            product_input.size
            if product_input.size not in (None, "null", "None", "")
            else None
        )
        input_color = (
            product_input.color
            if product_input.color not in (None, "null", "None", "")
            else None
        )

        aggregated = aggregate_crawl_results(
            results=crawl_results,
            input_upc=product_input.upc,
            input_brand=product_input.brand_name,
            input_name=product_input.name,
            input_size=input_size,
            input_color=input_color,
        )

        # Step 4: Fetch image if missing
        from app.image_fetcher import image_fetcher

        image_url = aggregated.get("image_url")
        if not image_url:
            print(f"[ImageFetcher] No image found, searching...")

            # Check if this is a gift set (harder to find)
            is_gift_set = any(
                word in product_input.name.lower()
                for word in ["gift", "set", "kit", "duo", "trio"]
            )

            if is_gift_set:
                image_url = await image_fetcher.fetch_image_for_gift_set(
                    brand=product_input.brand_name,
                    product_name=product_input.name,
                    upc=product_input.upc,
                )
            else:
                image_url = await image_fetcher.fetch_image(
                    brand=product_input.brand_name,
                    product_name=product_input.name,
                    existing_url=None,
                )

            if image_url:
                print(f"[ImageFetcher] Found image: {image_url[:60]}...")
                aggregated["image_url"] = image_url
            else:
                print(f"[ImageFetcher] Could not find image")

        # Step 4b: Validate/improve MSRP - enforce minimum price floor
        # But trust UPC database prices (they're authoritative)
        from app.msrp_lookup import msrp_lookup

        current_msrp = aggregated.get("msrp")

        # Check if we have a UPC-verified price (most reliable)
        has_upc_price = any(
            s.get("found_upc", False) for s in aggregated.get("sources", [])
        )

        # Get minimum expected price for this product type
        min_expected = msrp_lookup.get_min_expected_price(product_input.name)

        # Only apply floor if:
        # 1. No UPC-verified price (UPC prices are authoritative)
        # 2. Current price is suspiciously low
        if (
            current_msrp
            and min_expected
            and current_msrp < min_expected
            and not has_upc_price
        ):
            print(
                f"[MSRP] Price ${current_msrp:.2f} below minimum ${min_expected:.2f} for product type"
            )
            print(f"[MSRP] Searching authoritative retailers...")

            # Try to find better price from authoritative sources
            better_msrp, source = await msrp_lookup.lookup_msrp(
                brand=product_input.brand_name,
                product_name=product_input.name,
                current_prices=[current_msrp],
            )

            if better_msrp and better_msrp >= min_expected:
                print(f"[MSRP] Found better price: ${better_msrp:.2f} from {source}")
                aggregated["msrp"] = better_msrp
            else:
                # Use minimum expected price as floor
                print(f"[MSRP] Using minimum expected price: ${min_expected:.2f}")
                aggregated["msrp"] = min_expected
        elif has_upc_price:
            print(f"[MSRP] Trusting UPC database price: ${current_msrp:.2f}")

        # Step 5: Verify image using AI (if we have an image)
        image_verification = None
        if aggregated.get("image_url"):
            print(f"[AI] Verifying image with CLIP: {aggregated['image_url'][:50]}...")
            image_result = await image_client.verify_image(
                image_url=aggregated["image_url"],
                expected_brand=product_input.brand_name,
                expected_product=product_input.name,
                expected_color=input_color,
                expected_size=input_size,
            )

            image_verification = ImageVerificationInfo(
                is_verified=image_result.is_verified,
                confidence=image_result.confidence,
                brand_detected=image_result.brand_detected,
                product_detected=image_result.product_detected,
                reasoning=image_result.reasoning,
            )

            print(
                f"[AI] Image verification: verified={image_result.is_verified}, confidence={image_result.confidence}%"
            )

        # Step 5: Save to DB only if high confidence AND verified
        verification = aggregated.get("verification")
        is_verified = verification and verification.get("is_exact_match", False)

        # Boost or reduce confidence based on image verification
        final_confidence = aggregated["confidence"]
        if image_verification:
            if image_verification.is_verified and image_verification.confidence > 70:
                final_confidence = min(100, final_confidence + 5)  # Boost
            elif (
                not image_verification.is_verified
                and image_verification.confidence < 50
            ):
                final_confidence = max(0, final_confidence - 10)  # Reduce

        if final_confidence >= 85 and is_verified:
            await self._save_to_db(product_input, aggregated, db)

        # Step 6: Return output
        return ProductOutput(
            upc=product_input.upc,
            brand=product_input.brand_name,
            product_name=product_input.name,
            size=product_input.size,
            color=product_input.color,
            msrp=aggregated["msrp"],
            image_url=aggregated["image_url"],
            description=aggregated["description"],
            confidence_score=final_confidence,
            reasoning=aggregated["reasoning"],
            sources=[CrawlSource(**source) for source in aggregated["sources"]],
            verification=VerificationInfo(**verification) if verification else None,
            image_verification=image_verification,
        )

    async def _get_from_db(
        self, upc: str, db: AsyncSession
    ) -> Optional[EnrichedProduct]:
        """Get existing product from database."""
        stmt = select(EnrichedProduct).where(EnrichedProduct.upc == upc)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _save_to_db(
        self, product_input: ProductInput, aggregated: dict, db: AsyncSession
    ) -> None:
        """Save enriched product to database."""

        product = EnrichedProduct(
            upc=product_input.upc,
            brand=product_input.brand_name,
            product_name=product_input.name,
            size=product_input.size,
            color=product_input.color,
            msrp=aggregated["msrp"],
            image_url=aggregated["image_url"],
            description=aggregated["description"],
            confidence_score=aggregated["confidence"],
            sources={"sources": aggregated["sources"]},
            source_count=len(aggregated["sources"]),
        )

        db.add(product)
        await db.commit()
        print(
            f"[DB] Saved UPC {product_input.upc} with confidence {aggregated['confidence']} (VERIFIED)"
        )

    def _db_to_output(self, product: EnrichedProduct) -> ProductOutput:
        """Convert database model to output schema."""

        # Extract sources from JSON
        sources_data = product.sources.get("sources", [])
        sources = [CrawlSource(**s) for s in sources_data]

        return ProductOutput(
            upc=product.upc,
            brand=product.brand,
            product_name=product.product_name,
            size=product.size,
            color=product.color,
            msrp=float(product.msrp) if product.msrp else None,
            image_url=product.image_url,
            description=product.description,
            confidence_score=product.confidence_score,
            reasoning=f"Cached result from {product.source_count} verified sources",
            sources=sources,
            verification=VerificationInfo(
                is_exact_match=True,  # Only verified matches are cached
                brand_match=True,
                size_match=True,
                color_match=True,
                mismatches=[],
            ),
            image_verification=None,  # Not stored in cache, would need re-verification
        )

    async def close(self) -> None:
        """Cleanup resources."""
        await self.crawler_manager.close_all()
