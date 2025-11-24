"""
Google Shopping crawler implementation.

Google Shopping is more reliable than retailer sites because:
1. No heavy JavaScript requirements
2. Less aggressive bot blocking
3. Aggregates data from multiple retailers
"""
import re
import json
from typing import List, Optional
from urllib.parse import quote
from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, CrawlResult


class GoogleShoppingCrawler(BaseCrawler):
    """Crawler for Google Shopping."""
    
    def __init__(self) -> None:
        super().__init__("google_shopping")
    
    async def search_by_upc(self, upc: str) -> List[CrawlResult]:
        """
        Search Google Shopping by UPC.
        
        Google Shopping allows direct UPC searches.
        """
        # Search with just UPC
        results = await self._search(upc)
        
        return results
    
    async def search_by_name(self, brand: str, product_name: str) -> List[CrawlResult]:
        """
        Search Google Shopping by brand + product name.
        
        Useful as fallback when UPC search returns nothing.
        """
        query = f"{brand} {product_name}"
        return await self._search(query)
    
    async def _search(self, query: str) -> List[CrawlResult]:
        """Perform Google Shopping search."""
        
        url = f"https://www.google.com/search?tbm=shop&q={quote(query)}"
        
        html = await self.fetch(url)
        if not html:
            return []
        
        return self._parse_shopping_results(html, query)
    
    def _parse_shopping_results(self, html: str, query: str) -> List[CrawlResult]:
        """Parse Google Shopping search results."""
        
        soup = BeautifulSoup(html, 'html.parser')
        results: List[CrawlResult] = []
        
        # Google Shopping uses various div structures
        # Try multiple selectors
        
        # Method 1: Look for product cards with prices
        product_cards = soup.select('div.sh-dgr__content')
        
        if not product_cards:
            # Method 2: Alternative selector
            product_cards = soup.select('div.sh-dlr__list-result')
        
        if not product_cards:
            # Method 3: Look for any div with price pattern
            product_cards = soup.find_all('div', class_=lambda x: x and 'sh-' in x)
        
        for card in product_cards[:5]:  # Limit to top 5
            result = self._parse_product_card(card, query)
            if result:
                results.append(result)
        
        # If no structured results, try to extract any price/product info
        if not results:
            result = self._fallback_extraction(soup, query)
            if result:
                results.append(result)
        
        return results
    
    def _parse_product_card(self, card: BeautifulSoup, query: str) -> Optional[CrawlResult]:
        """Parse a single product card from Google Shopping."""
        
        try:
            # Extract title
            title_elem = card.select_one('h3') or card.select_one('h4') or card.select_one('a')
            title = title_elem.text.strip() if title_elem else None
            
            # Extract price
            price = None
            price_text = card.get_text()
            price_match = re.search(r'\$(\d+(?:\.\d{2})?)', price_text)
            if price_match:
                try:
                    price = float(price_match.group(1))
                except ValueError:
                    pass
            
            # Extract image
            image_url = None
            img_elem = card.select_one('img')
            if img_elem:
                image_url = img_elem.get('src') or img_elem.get('data-src')
            
            # Extract link
            url = None
            link_elem = card.select_one('a[href]')
            if link_elem:
                href = link_elem.get('href', '')
                if href.startswith('/'):
                    url = f"https://www.google.com{href}"
                elif href.startswith('http'):
                    url = href
            
            # Extract seller/source
            seller = None
            seller_elem = card.select_one('div.aULzUe') or card.select_one('div.E5ocAb')
            if seller_elem:
                seller = seller_elem.text.strip()
            
            if title or price:
                return CrawlResult(
                    source=f"google_shopping ({seller})" if seller else "google_shopping",
                    url=url or f"https://www.google.com/search?tbm=shop&q={quote(query)}",
                    found_upc=False,  # Google doesn't expose UPC directly
                    upc=None,
                    title=title,
                    price=price,
                    image_url=image_url,
                    description=None,
                )
            
        except Exception as e:
            print(f"[google_shopping] Error parsing card: {e}")
        
        return None
    
    def _fallback_extraction(self, soup: BeautifulSoup, query: str) -> Optional[CrawlResult]:
        """
        Fallback extraction when structured parsing fails.
        
        Just try to find any price on the page.
        """
        page_text = soup.get_text()
        
        # Find all prices
        prices = re.findall(r'\$(\d+(?:\.\d{2})?)', page_text)
        
        if prices:
            # Take the most common price (likely MSRP)
            price_counts = {}
            for p in prices:
                price_counts[p] = price_counts.get(p, 0) + 1
            
            most_common_price = max(price_counts, key=price_counts.get)
            
            # Find any image
            img = soup.select_one('img[src*="encrypted"]') or soup.select_one('img[src*="gstatic"]')
            image_url = img.get('src') if img else None
            
            return CrawlResult(
                source="google_shopping",
                url=f"https://www.google.com/search?tbm=shop&q={quote(query)}",
                found_upc=False,
                upc=None,
                title=query,  # Use query as title
                price=float(most_common_price),
                image_url=image_url,
                description=None,
            )
        
        return None
    
    def parse_product_page(self, html: str, url: str) -> Optional[CrawlResult]:
        """Not used for Google Shopping (we parse search results directly)."""
        return None
