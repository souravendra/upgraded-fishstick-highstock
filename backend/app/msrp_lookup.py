"""
MSRP lookup module.

Tries to find the true MSRP from authoritative sources:
1. Official brand websites
2. Major retailers (Sephora, Ulta, Nordstrom)
3. Price comparison sites

The key insight: MSRP is the HIGHEST legitimate retail price.
Sale prices, clearance, and third-party sellers are always lower.
"""

import re
import httpx
from typing import Optional, List, Tuple
from urllib.parse import quote
from bs4 import BeautifulSoup


class MSRPLookup:
    """
    Looks up MSRP from authoritative sources.
    """

    # Known beauty retailer price patterns
    PRICE_SELECTORS = {
        "sephora": [
            'span[data-at="price"]',
            ".css-0.e65hsk0",  # Sephora's price class
            "span.css-1jczs19",
        ],
        "ulta": [
            ".ProductPricing",
            "span.ProductPricingPaid",
            ".product-price",
        ],
        "nordstrom": [
            'span[itemprop="price"]',
            ".product-price",
        ],
    }

    # Major retailers to check (in order of trustworthiness)
    AUTHORITATIVE_RETAILERS = [
        ("sephora", "https://www.google.com/search?q=site:sephora.com+{query}"),
        ("ulta", "https://www.google.com/search?q=site:ulta.com+{query}"),
        ("nordstrom", "https://www.google.com/search?q=site:nordstrom.com+{query}"),
        ("macys", "https://www.google.com/search?q=site:macys.com+{query}"),
    ]

    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )

    async def lookup_msrp(
        self,
        brand: str,
        product_name: str,
        current_prices: List[float],
    ) -> Tuple[Optional[float], str]:
        """
        Look up MSRP from authoritative sources.

        Args:
            brand: Product brand
            product_name: Product name
            current_prices: Prices we've already found

        Returns:
            (msrp, source) - The MSRP and where it came from
        """
        all_prices: List[Tuple[float, str]] = []

        # Add current prices
        for p in current_prices:
            all_prices.append((p, "crawler"))

        # Search authoritative retailers
        query = f"{brand} {product_name}".split("-")[0].strip()
        query = re.sub(r"[#/]", " ", query)

        for retailer, url_template in self.AUTHORITATIVE_RETAILERS:
            try:
                price = await self._search_retailer(retailer, url_template, query)
                if price:
                    all_prices.append((price, retailer))
                    print(f"  [MSRP] Found ${price:.2f} from {retailer}")
            except Exception as e:
                print(f"  [MSRP] {retailer} error: {e}")

        if not all_prices:
            return None, "none"

        # MSRP strategy:
        # 1. Prefer prices from authoritative retailers
        # 2. Use the highest price from authoritative sources
        # 3. Filter out outliers (> 3x median = probably bundle)

        retailer_prices = [(p, s) for p, s in all_prices if s != "crawler"]

        if retailer_prices:
            # Use max from authoritative retailers
            best = max(retailer_prices, key=lambda x: x[0])
            return best

        # Fallback to crawled prices
        prices = [p for p, s in all_prices]
        median = sorted(prices)[len(prices) // 2]
        reasonable = [p for p in prices if p <= median * 3]

        if reasonable:
            return max(reasonable), "crawler"

        return max(prices), "crawler"

    async def _search_retailer(
        self, retailer: str, url_template: str, query: str
    ) -> Optional[float]:
        """Search a specific retailer for price."""

        url = url_template.format(query=quote(query))

        try:
            response = await self.client.get(url)
            if response.status_code != 200:
                return None

            html = response.text

            # Extract prices from Google search results
            # Google often shows prices in snippets
            prices = self._extract_prices_from_text(html)

            if prices:
                # Return the most common/median price
                prices.sort()
                return prices[len(prices) // 2]

            return None

        except Exception:
            return None

    def _extract_prices_from_text(self, text: str) -> List[float]:
        """Extract all USD prices from text."""

        # Find all price patterns
        patterns = [
            r"\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)",  # $12.99 or $1,299.99
            r"USD\s*(\d+(?:\.\d{2})?)",  # USD 12.99
            r"(\d+(?:\.\d{2})?)\s*dollars",  # 12.99 dollars
        ]

        prices = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    price = float(match.replace(",", ""))
                    # Filter unreasonable prices for beauty products
                    if 1 <= price <= 500:  # Beauty products typically $1-$500
                        prices.append(price)
                except ValueError:
                    pass

        return prices

    async def validate_price(
        self,
        price: float,
        brand: str,
        product_type: str,
    ) -> Tuple[bool, str]:
        """
        Validate if a price is reasonable for the product type.

        Returns:
            (is_valid, reason)
        """
        # Price ranges for common beauty product types
        PRICE_RANGES = {
            "lip liner": (8, 40),
            "lipstick": (8, 50),
            "foundation": (15, 80),
            "mascara": (8, 40),
            "eyeshadow": (10, 60),
            "mask": (10, 60),
            "mud mask": (15, 50),
            "cleanser": (10, 60),
            "moisturizer": (15, 100),
            "serum": (20, 150),
            "fragrance": (30, 300),
            "gift set": (30, 200),
            "default": (5, 200),
        }

        # Find matching product type
        product_lower = product_type.lower()
        expected_range = PRICE_RANGES["default"]

        for key, range_val in PRICE_RANGES.items():
            if key in product_lower:
                expected_range = range_val
                break

        min_price, max_price = expected_range

        if price < min_price:
            return (
                False,
                f"Price ${price:.2f} below typical range ${min_price}-${max_price}",
            )
        elif price > max_price:
            return (
                False,
                f"Price ${price:.2f} above typical range ${min_price}-${max_price}",
            )

        return True, "Price within expected range"

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()

    def get_min_expected_price(self, product_type: str) -> Optional[float]:
        """
        Get the minimum expected price for a product type.
        Used as a fallback when we can't find a better price.

        These are conservative minimums - actual MSRP is often higher.
        """
        product_lower = product_type.lower()

        # Check specific patterns first (order matters!)
        # More specific → less specific
        PRICE_MINIMUMS = [
            ("mud mask", 24),  # Mud masks $24-35
            ("sheet mask", 15),  # Sheet masks $15-25
            ("face mask", 22),  # Face masks $22-40
            ("mask", 20),  # Generic masks $20+
            ("lip liner", 14),  # Premium lip liners $14-25
            ("lip gloss", 14),  # Lip gloss $14-28
            ("lipstick", 14),  # Premium lipsticks $14-40
            ("lip", 14),  # Generic lip products $14+
            ("foundation", 25),  # Premium foundations $25-60
            ("mascara", 14),  # Premium mascara $14-30
            ("eyeshadow", 18),  # Premium eyeshadow $18-50
            ("cleanser", 18),  # Premium cleansers $18-45
            ("moisturizer", 22),  # Premium moisturizers $22-80
            ("serum", 30),  # Serums $30-150
            ("eau de parfum", 60),  # EDP $60-200
            ("eau de toilette", 45),  # EDT $45-150
            ("fragrance", 50),  # Fragrances $50-200
            ("perfume", 50),  # Perfumes $50-200
            ("cologne", 45),  # Cologne $45-150
            ("gift set", 45),  # Gift sets $45-200
            ("palette", 25),  # Makeup palettes $25-65
            ("primer", 20),  # Primers $20-45
            ("concealer", 16),  # Concealers $16-35
            ("blush", 18),  # Blush $18-40
            ("bronzer", 20),  # Bronzer $20-45
            ("highlighter", 20),  # Highlighter $20-45
            ("setting spray", 18),  # Setting sprays $18-35
            ("setting powder", 20),  # Setting powder $20-40
        ]

        for pattern, min_price in PRICE_MINIMUMS:
            if pattern in product_lower:
                return float(min_price)

        # Default minimum for unknown beauty products
        return 15.0


# Global instance
msrp_lookup = MSRPLookup()
