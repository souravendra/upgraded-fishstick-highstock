"""
Crawler manager - orchestrates multiple crawlers.
"""

import asyncio
from typing import List, Dict, Any, Optional

from app.crawlers.base import CrawlResult
from app.crawlers.sephora import SephoraCrawler
from app.crawlers.google_shopping import GoogleShoppingCrawler
from app.crawlers.upc_database import UPCDatabaseCrawler
from app.verification import product_verifier, VerificationResult


class CrawlerManager:
    """Manages multiple crawlers and orchestrates searches."""

    def __init__(self) -> None:
        self.sephora = SephoraCrawler()
        self.google_shopping = GoogleShoppingCrawler()
        self.upc_database = UPCDatabaseCrawler()

        # All crawlers for parallel search
        self.all_crawlers = [
            self.sephora,
            self.google_shopping,
            self.upc_database,
        ]

    async def search_all(
        self, upc: str, brand: Optional[str] = None, product_name: Optional[str] = None
    ) -> List[CrawlResult]:
        """
        Search all crawlers in parallel for a UPC.

        Strategy:
        1. Search by UPC across all sources
        2. ALSO search by brand+name (in parallel)
        3. Combine and deduplicate results

        Returns combined results from all sources.
        """
        print(f"[CrawlerManager] Starting search for UPC: {upc}")

        # Step 1: Try UPC search
        upc_results = await self._search_by_upc(upc)

        # Step 2: ALSO try brand+name search (more likely to find results)
        name_results: List[CrawlResult] = []
        if brand and product_name:
            print(
                f"[CrawlerManager] Also searching by brand+name: {brand} {product_name}"
            )
            name_results = await self._search_by_name(brand, product_name)

        # Combine results (UPC results first - more authoritative)
        all_results = upc_results + name_results

        # Filter out duplicates (same source + similar price)
        seen = set()
        unique_results: List[CrawlResult] = []
        for r in all_results:
            key = (
                r.source.split("(")[0].strip(),
                r.price,
            )  # Dedupe by source and price
            if key not in seen:
                seen.add(key)
                unique_results.append(r)

        print(
            f"[CrawlerManager] Total results: {len(unique_results)} (UPC: {len(upc_results)}, Name: {len(name_results)})"
        )
        return unique_results

    async def _search_by_upc(self, upc: str) -> List[CrawlResult]:
        """Search all crawlers by UPC."""

        tasks = [
            self.sephora.search_by_upc(upc),
            self.google_shopping.search_by_upc(upc),
            self.upc_database.search_by_upc(upc),
        ]

        return await self._gather_results(tasks)

    async def _search_by_name(self, brand: str, product_name: str) -> List[CrawlResult]:
        """Search by brand + product name."""

        # Extract just the core product name (remove size, color, etc.)
        # "No Pressure Lip Liner - #1 - On the Rose" -> "No Pressure Lip Liner"
        core_name = product_name.split("-")[0].strip()
        core_name = core_name.split("/")[0].strip()

        tasks = [
            self.google_shopping.search_by_name(brand, core_name),
            self.google_shopping.search_by_name(brand, product_name),  # Full name too
        ]

        return await self._gather_results(tasks)

    async def _gather_results(self, tasks: list) -> List[CrawlResult]:
        """Gather results from multiple tasks with timeout."""

        try:
            results_list = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=30.0
            )
        except asyncio.TimeoutError:
            print("[CrawlerManager] Timeout - using partial results")
            return []

        # Flatten and filter
        all_results: List[CrawlResult] = []
        for results in results_list:
            if isinstance(results, list):
                all_results.extend(results)
                for r in results:
                    print(f"  [+] {r.source}: {r.title} - ${r.price}")
            elif isinstance(results, Exception):
                print(f"  [!] Crawler error: {results}")

        return all_results

    async def close_all(self) -> None:
        """Close all crawler HTTP clients."""
        for crawler in self.all_crawlers:
            await crawler.close()


def aggregate_crawl_results(
    results: List[CrawlResult],
    input_upc: str,
    input_brand: str,
    input_name: str,
    input_size: Optional[str] = None,
    input_color: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Aggregate results from multiple crawlers WITH VERIFICATION.

    Critical requirement: Only return high confidence if:
    - Brand matches exactly
    - Size/volume matches (if provided)
    - Color/shade matches (if provided)

    Strategy:
    1. Filter out garbage results (no real content)
    2. Verify each result against input attributes
    3. Only count verified matches
    4. Return confidence based on verification quality
    """
    # Normalize null strings
    input_size = None if input_size in (None, "null", "None", "") else input_size
    input_color = None if input_color in (None, "null", "None", "") else input_color

    if not results:
        return {
            "confidence": 0,
            "reasoning": "No results found from any source",
            "msrp": None,
            "image_url": None,
            "description": None,
            "sources": [],
            "verification": None,
        }

    # Filter out garbage results (title/description is just UPC or empty)
    valid_results = []
    for r in results:
        title = (r.title or "").strip()
        desc = (r.description or "").strip()

        # Skip if title is just the UPC
        if title == input_upc or title == "":
            print(f"  [Filter] Skipping {r.source}: title is empty or just UPC")
            continue

        # Skip if description is just the UPC and no real title
        if desc == input_upc and len(title) < 10:
            print(f"  [Filter] Skipping {r.source}: no real content")
            continue

        valid_results.append(r)

    if not valid_results:
        return {
            "confidence": 0,
            "reasoning": "No valid results found (only garbage data)",
            "msrp": None,
            "image_url": None,
            "description": None,
            "sources": [
                {"name": r.source, "url": r.url, "found_upc": r.found_upc}
                for r in results
            ],
            "verification": None,
        }

    results = valid_results

    # Verify each result
    verified_results: List[tuple[CrawlResult, VerificationResult]] = []

    for result in results:
        verification = product_verifier.verify_match(
            input_brand=input_brand,
            input_name=input_name,
            input_size=input_size,
            input_color=input_color,
            found_title=result.title,
            found_description=result.description,
            found_upc_match=result.found_upc,  # Pass UPC match status!
        )

        print(
            f"  [Verify] {result.source}: match={verification.is_exact_match}, "
            f"confidence={verification.confidence}, upc_match={result.found_upc}, mismatches={verification.mismatches}"
        )

        verified_results.append((result, verification))

    # Sort by verification confidence
    verified_results.sort(key=lambda x: x[1].confidence, reverse=True)

    # Filter to exact matches only
    exact_matches = [(r, v) for r, v in verified_results if v.is_exact_match]

    # Also consider high-confidence near-matches (brand match + one attribute)
    high_confidence = [(r, v) for r, v in verified_results if v.confidence >= 70]

    if exact_matches:
        # HIGH CONFIDENCE: We have verified exact matches
        return _aggregate_verified_results(exact_matches, input_upc, is_exact=True)

    elif high_confidence:
        # MEDIUM CONFIDENCE: Brand matches, some attributes verified
        return _aggregate_verified_results(high_confidence, input_upc, is_exact=False)

    elif verified_results:
        # LOW CONFIDENCE: Results found but verification failed
        best_result, best_verification = verified_results[0]
        return {
            "confidence": best_verification.confidence,
            "reasoning": f"VERIFICATION FAILED: {best_verification.reasoning}",
            "msrp": best_result.price,
            "image_url": best_result.image_url,
            "description": best_result.description or best_result.title,
            "sources": [
                {
                    "name": best_result.source,
                    "url": best_result.url,
                    "found_upc": best_result.found_upc,
                }
            ],
            "verification": {
                "is_exact_match": False,
                "brand_match": best_verification.brand_match,
                "size_match": best_verification.size_match,
                "color_match": best_verification.color_match,
                "mismatches": best_verification.mismatches,
            },
        }

    else:
        return {
            "confidence": 0,
            "reasoning": "No results found from any source",
            "msrp": None,
            "image_url": None,
            "description": None,
            "sources": [],
            "verification": None,
        }


def _aggregate_verified_results(
    verified_results: List[tuple[CrawlResult, VerificationResult]],
    input_upc: str,
    is_exact: bool,
) -> Dict[str, Any]:
    """Aggregate verified results."""

    results = [r for r, v in verified_results]
    verifications = [v for r, v in verified_results]

    # Get best verification
    best_verification = verifications[0]

    # Pick MSRP (Manufacturer's Suggested Retail Price)
    # Priority:
    # 1. UPC database prices (most reliable for MSRP)
    # 2. Highest "reasonable" price from other sources

    # First, check for UPC database price (most authoritative)
    upc_prices = [
        r.price for r in results if r.found_upc and r.price is not None and r.price > 0
    ]
    other_prices = [
        r.price
        for r in results
        if not r.found_upc and r.price is not None and r.price > 0
    ]

    msrp = None

    if upc_prices:
        # UPC database prices are most reliable - use the highest one
        msrp = max(upc_prices)
        print(f"  [MSRP] Using UPC database price: ${msrp:.2f}")
    elif other_prices:
        # Fallback to other sources - use highest reasonable price
        other_prices.sort()

        # Filter outliers: remove prices > 3x the median (likely bundles)
        median = other_prices[len(other_prices) // 2]
        reasonable_prices = [p for p in other_prices if p <= median * 3]

        if reasonable_prices:
            # MSRP is typically the highest legitimate retail price
            if len(reasonable_prices) >= 4:
                # Use 75th percentile to avoid outlier highs
                idx = int(len(reasonable_prices) * 0.75)
                msrp = reasonable_prices[idx]
            else:
                # With few prices, use the max
                msrp = max(reasonable_prices)
        else:
            msrp = max(other_prices)  # Fallback

        print(f"  [MSRP] Using crawled price: ${msrp:.2f}")

    # Pick best image
    image_url = next((r.image_url for r in results if r.image_url), None)

    # Pick best description
    descriptions = [
        r.description or r.title for r in results if r.description or r.title
    ]
    description = max(descriptions, key=len) if descriptions else None

    # Build sources list
    sources = [
        {"name": r.source, "url": r.url, "found_upc": r.found_upc} for r in results
    ]

    # Calculate final confidence
    if is_exact:
        confidence = 95 if len(results) >= 2 else 85
        reasoning = f"VERIFIED: Exact match confirmed on {len(results)} source(s) - {best_verification.reasoning}"
    else:
        confidence = best_verification.confidence
        reasoning = f"PARTIAL MATCH: {best_verification.reasoning}"

    return {
        "confidence": confidence,
        "reasoning": reasoning,
        "msrp": msrp,
        "image_url": image_url,
        "description": description,
        "sources": sources,
        "verification": {
            "is_exact_match": is_exact,
            "brand_match": best_verification.brand_match,
            "size_match": best_verification.size_match,
            "color_match": best_verification.color_match,
            "mismatches": best_verification.mismatches,
        },
    }
