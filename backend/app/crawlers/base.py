"""
Base crawler class for web scraping.
"""
import httpx
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse, quote
from bs4 import BeautifulSoup
import asyncio
import random

from app.rate_limiter import rate_limiter


class CrawlResult:
    """Result from crawling a product page."""
    
    def __init__(
        self,
        source: str,
        url: str,
        found_upc: bool,
        upc: Optional[str] = None,
        title: Optional[str] = None,
        price: Optional[float] = None,
        image_url: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        self.source = source
        self.url = url
        self.found_upc = found_upc
        self.upc = upc
        self.title = title
        self.price = price
        self.image_url = image_url
        self.description = description
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'source': self.source,
            'url': self.url,
            'found_upc': self.found_upc,
            'upc': self.upc,
            'title': self.title,
            'price': self.price,
            'image_url': self.image_url,
            'description': self.description,
        }


class BaseCrawler(ABC):
    """Base class for all crawlers."""
    
    def __init__(self, source_name: str) -> None:
        self.source_name = source_name
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers=self._get_default_headers()
        )
    
    def _get_default_headers(self) -> Dict[str, str]:
        """Get default HTTP headers."""
        user_agents = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        
        return {
            "User-Agent": random.choice(user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    
    async def fetch(self, url: str) -> Optional[str]:
        """
        Fetch URL with rate limiting and error handling.
        
        Returns HTML content or None if fetch failed.
        """
        domain = urlparse(url).netloc
        limiter = rate_limiter.get_limiter(domain)
        
        await limiter.acquire()
        
        try:
            # Random jitter (human-like behavior)
            await asyncio.sleep(random.uniform(0.1, 0.3))
            
            response = await self.client.get(url, headers=self._get_default_headers())
            
            if response.status_code == 200:
                return response.text
            else:
                print(f"[{self.source_name}] HTTP {response.status_code} for {url}")
                return None
                
        except httpx.TimeoutException:
            print(f"[{self.source_name}] Timeout fetching {url}")
            return None
        except Exception as e:
            print(f"[{self.source_name}] Error fetching {url}: {e}")
            return None
        finally:
            limiter.release()
    
    @abstractmethod
    async def search_by_upc(self, upc: str) -> List[CrawlResult]:
        """
        Search for product by UPC.
        
        Must be implemented by each crawler.
        """
        pass
    
    @abstractmethod
    def parse_product_page(self, html: str, url: str) -> Optional[CrawlResult]:
        """
        Parse product page HTML.
        
        Must be implemented by each crawler.
        """
        pass
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
