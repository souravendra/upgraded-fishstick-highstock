"""
Image fetcher module.

Tries multiple strategies to find a product image:
1. Use image from crawl results (if available)
2. Search Google Images
3. Fetch from known retailer sites
"""

import re
import httpx
from typing import Optional, List
from urllib.parse import quote
from bs4 import BeautifulSoup


class ImageFetcher:
    """
    Fetches product images using multiple strategies.
    """

    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        )

    async def fetch_image(
        self,
        brand: str,
        product_name: str,
        existing_url: Optional[str] = None,
    ) -> Optional[str]:
        """
        Fetch product image URL using multiple strategies.

        Args:
            brand: Product brand
            product_name: Product name
            existing_url: Existing image URL from crawl (if any)

        Returns:
            Image URL or None
        """
        # Strategy 1: Use existing URL if valid
        if existing_url and await self._is_valid_image(existing_url):
            return existing_url

        # Strategy 2: Google Images search
        image_url = await self._search_google_images(brand, product_name)
        if image_url:
            return image_url

        # Strategy 3: Try direct retailer search
        image_url = await self._search_sephora_images(brand, product_name)
        if image_url:
            return image_url

        return None

    async def _is_valid_image(self, url: str) -> bool:
        """Check if image URL is valid and accessible."""
        if not url or not url.startswith("http"):
            return False

        try:
            response = await self.client.head(url)
            content_type = response.headers.get("content-type", "")
            return response.status_code == 200 and "image" in content_type
        except Exception:
            return False

    async def _search_google_images(
        self, brand: str, product_name: str
    ) -> Optional[str]:
        """Search Google Images for product."""

        # Clean up product name for search
        query = f"{brand} {product_name}".replace("-", " ")
        query = re.sub(r"[#/]", " ", query)
        query = " ".join(query.split())  # Normalize whitespace

        url = f"https://www.google.com/search?q={quote(query)}&tbm=isch"

        try:
            response = await self.client.get(url)
            if response.status_code != 200:
                return None

            html = response.text

            # Google Images embeds image URLs in various ways
            # Try to extract from the page

            # Method 1: Look for direct image URLs in data attributes
            soup = BeautifulSoup(html, "html.parser")

            # Find image elements
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src")
                if src and src.startswith("http") and "gstatic" not in src:
                    # Skip Google's own images
                    if "google.com" not in src and "gstatic.com" not in src:
                        return src

            # Method 2: Look for encoded image URLs in scripts
            # Google often includes full URLs in JSON data
            import json

            for script in soup.find_all("script"):
                if script.string and "http" in (script.string or ""):
                    # Look for image URLs in the script
                    urls = re.findall(
                        r'https?://[^"\'<>\s]+\.(?:jpg|jpeg|png|webp)', script.string
                    )
                    for img_url in urls:
                        # Skip Google's own images
                        if "gstatic.com" not in img_url and "google.com" not in img_url:
                            # Unescape the URL
                            img_url = img_url.replace("\\u003d", "=").replace(
                                "\\u0026", "&"
                            )
                            return img_url

            return None

        except Exception as e:
            print(f"[ImageFetcher] Google Images error: {e}")
            return None

    async def _search_sephora_images(
        self, brand: str, product_name: str
    ) -> Optional[str]:
        """Try to find image from Sephora."""

        query = f"{brand} {product_name}".split("-")[0].strip()
        url = f"https://www.sephora.com/search?keyword={quote(query)}"

        try:
            response = await self.client.get(url)
            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.text, "html.parser")

            # Look for product images
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src")
                if src and "sephora" in src and ("product" in src or "sku" in src):
                    # Make sure it's a full URL
                    if not src.startswith("http"):
                        src = "https://www.sephora.com" + src
                    return src

            return None

        except Exception as e:
            print(f"[ImageFetcher] Sephora error: {e}")
            return None

    async def fetch_image_for_gift_set(
        self,
        brand: str,
        product_name: str,
        upc: str,
    ) -> Optional[str]:
        """
        Special handling for gift sets which are harder to find.

        Tries:
        1. Brand's official site
        2. Fragrance/beauty databases
        3. Major retailers
        """

        # Try multiple search variations
        search_terms = [
            f"{brand} {product_name}",
            f"{brand} gift set {upc}",
            f"{brand} holiday set",
        ]

        for term in search_terms:
            image_url = await self._search_google_images(brand, term)
            if image_url:
                return image_url

        # Try specific retailers for fragrances/gift sets
        if "dior" in brand.lower() or "sauvage" in product_name.lower():
            image_url = await self._search_fragrance_sites(brand, product_name)
            if image_url:
                return image_url

        return None

    async def _search_fragrance_sites(
        self, brand: str, product_name: str
    ) -> Optional[str]:
        """Search fragrance-specific sites for gift sets."""

        # Try FragranceNet
        query = f"{brand} {product_name}".replace(" ", "+")
        url = f"https://www.fragrancenet.com/search?q={query}"

        try:
            response = await self.client.get(url)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                for img in soup.find_all("img"):
                    src = img.get("src") or img.get("data-src")
                    if src and "fragrancenet" in src and ".jpg" in src:
                        if not src.startswith("http"):
                            src = "https://www.fragrancenet.com" + src
                        return src
        except Exception:
            pass

        return None

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()


# Global instance
image_fetcher = ImageFetcher()
