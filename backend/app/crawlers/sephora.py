"""
Sephora crawler implementation.
"""
import json
import re
from typing import List, Optional
from urllib.parse import quote
from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, CrawlResult


class SephoraCrawler(BaseCrawler):
    """Crawler for Sephora.com"""
    
    BASE_URL = "https://www.sephora.com"
    
    def __init__(self) -> None:
        super().__init__("sephora")
    
    async def search_by_upc(self, upc: str) -> List[CrawlResult]:
        """
        Search Sephora by UPC.
        
        Strategy:
        1. Search using UPC as keyword
        2. Parse search results page
        3. Extract product links
        4. Fetch top 2 product pages
        """
        search_url = f"{self.BASE_URL}/search?keyword={quote(upc)}"
        
        html = await self.fetch(search_url)
        if not html:
            return []
        
        # Extract product URLs from search results
        product_urls = self._extract_product_urls(html)
        
        # Fetch each product page (limit to 2)
        results: List[CrawlResult] = []
        for url in product_urls[:2]:
            result = await self._fetch_product_page(url, upc)
            if result:
                results.append(result)
        
        return results
    
    def _extract_product_urls(self, html: str) -> List[str]:
        """Extract product URLs from search results."""
        soup = BeautifulSoup(html, 'html.parser')
        urls: List[str] = []
        
        # Sephora uses data-at attributes for product links
        # This is a simplified selector - real implementation may need adjustment
        links = soup.select('a[href*="/product/"]')
        
        for link in links:
            href = link.get('href')
            if href:
                # Handle relative URLs
                if href.startswith('/'):
                    href = self.BASE_URL + href
                urls.append(href)
        
        return list(set(urls))  # Remove duplicates
    
    async def _fetch_product_page(self, url: str, expected_upc: str) -> Optional[CrawlResult]:
        """Fetch and parse a product page."""
        html = await self.fetch(url)
        if not html:
            return None
        
        return self.parse_product_page(html, url, expected_upc)
    
    def parse_product_page(
        self, 
        html: str, 
        url: str,
        expected_upc: Optional[str] = None
    ) -> Optional[CrawlResult]:
        """
        Parse Sephora product page.
        
        Sephora typically has JSON-LD structured data which is easier to parse.
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # Try to find JSON-LD structured data
        json_ld = soup.find('script', type='application/ld+json')
        
        if json_ld:
            try:
                data = json.loads(json_ld.string)
                
                # Extract UPC if present
                upc = data.get('gtin13') or data.get('gtin12') or data.get('gtin')
                
                # Check if UPC matches (if we're looking for specific UPC)
                found_upc = False
                if expected_upc and upc:
                    found_upc = str(upc) == str(expected_upc)
                elif upc:
                    found_upc = True
                
                # Extract price
                price = None
                offers = data.get('offers', {})
                if isinstance(offers, dict):
                    price_str = offers.get('price')
                    if price_str:
                        try:
                            price = float(price_str)
                        except (ValueError, TypeError):
                            pass
                
                return CrawlResult(
                    source=self.source_name,
                    url=url,
                    found_upc=found_upc,
                    upc=str(upc) if upc else None,
                    title=data.get('name'),
                    price=price,
                    image_url=data.get('image'),
                    description=data.get('description'),
                )
                
            except json.JSONDecodeError:
                pass
        
        # Fallback: Try to extract from HTML structure
        return self._parse_html_fallback(soup, url, expected_upc)
    
    def _parse_html_fallback(
        self,
        soup: BeautifulSoup,
        url: str,
        expected_upc: Optional[str]
    ) -> Optional[CrawlResult]:
        """
        Fallback parsing using CSS selectors.
        
        Note: These selectors may need updates as Sephora changes their HTML.
        """
        title_elem = soup.select_one('h1[data-at="product_name"]')
        title = title_elem.text.strip() if title_elem else None
        
        price_elem = soup.select_one('div[data-at="price"]')
        price = None
        if price_elem:
            price_text = price_elem.text.strip()
            # Extract number from price text (e.g., "$16.00" -> 16.00)
            price_match = re.search(r'\$?(\d+\.?\d*)', price_text)
            if price_match:
                try:
                    price = float(price_match.group(1))
                except ValueError:
                    pass
        
        image_elem = soup.select_one('img[data-at="product_image"]')
        image_url = image_elem.get('src') if image_elem else None
        
        # Try to find UPC in page (often in metadata or product details)
        upc = None
        # This is challenging without structured data
        # Would need to search through product details section
        
        return CrawlResult(
            source=self.source_name,
            url=url,
            found_upc=False,  # Conservative - can't reliably verify UPC
            upc=upc,
            title=title,
            price=price,
            image_url=image_url,
            description=None,
        )
