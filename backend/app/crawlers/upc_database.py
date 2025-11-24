"""
UPC Database API crawler.

Uses free UPC lookup APIs as a source.
"""
import json
from typing import List, Optional

from app.crawlers.base import BaseCrawler, CrawlResult


class UPCDatabaseCrawler(BaseCrawler):
    """
    Crawler for UPC Database APIs.
    
    Tries multiple free UPC lookup services.
    """
    
    def __init__(self) -> None:
        super().__init__("upc_database")
    
    async def search_by_upc(self, upc: str) -> List[CrawlResult]:
        """
        Search multiple UPC database APIs.
        """
        results: List[CrawlResult] = []
        
        # Try UPCitemdb (free, no API key required for limited use)
        result = await self._search_upcitemdb(upc)
        if result:
            results.append(result)
        
        # Try Open Food Facts (works for some products)
        result = await self._search_openfoodfacts(upc)
        if result:
            results.append(result)
        
        return results
    
    async def _search_upcitemdb(self, upc: str) -> Optional[CrawlResult]:
        """
        Search UPCitemdb.com API.
        
        Free tier: 100 requests/day
        """
        url = f"https://api.upcitemdb.com/prod/trial/lookup?upc={upc}"
        
        try:
            response_text = await self.fetch(url)
            if not response_text:
                return None
            
            data = json.loads(response_text)
            
            if data.get('code') == 'OK' and data.get('items'):
                item = data['items'][0]
                
                # Extract price (they provide offers)
                price = None
                offers = item.get('offers', [])
                if offers:
                    prices = [o.get('price') for o in offers if o.get('price')]
                    if prices:
                        price = max(prices)  # MSRP is usually the highest
                
                # Get images
                images = item.get('images', [])
                image_url = images[0] if images else None
                
                return CrawlResult(
                    source="upcitemdb",
                    url=f"https://www.upcitemdb.com/upc/{upc}",
                    found_upc=True,
                    upc=upc,
                    title=item.get('title'),
                    price=price,
                    image_url=image_url,
                    description=item.get('description'),
                )
                
        except json.JSONDecodeError:
            print(f"[upcitemdb] Invalid JSON response for UPC {upc}")
        except Exception as e:
            print(f"[upcitemdb] Error: {e}")
        
        return None
    
    async def _search_openfoodfacts(self, upc: str) -> Optional[CrawlResult]:
        """
        Search Open Food Facts API.
        
        Works primarily for food/cosmetics with barcodes.
        Completely free, no limits.
        """
        url = f"https://world.openfoodfacts.org/api/v0/product/{upc}.json"
        
        try:
            response_text = await self.fetch(url)
            if not response_text:
                return None
            
            data = json.loads(response_text)
            
            if data.get('status') == 1 and data.get('product'):
                product = data['product']
                
                return CrawlResult(
                    source="openfoodfacts",
                    url=f"https://world.openfoodfacts.org/product/{upc}",
                    found_upc=True,
                    upc=upc,
                    title=product.get('product_name') or product.get('product_name_en'),
                    price=None,  # Open Food Facts doesn't have prices
                    image_url=product.get('image_url') or product.get('image_front_url'),
                    description=product.get('generic_name'),
                )
                
        except json.JSONDecodeError:
            pass  # Expected for products not in database
        except Exception as e:
            print(f"[openfoodfacts] Error: {e}")
        
        return None
    
    def parse_product_page(self, html: str, url: str) -> Optional[CrawlResult]:
        """Not used for API-based crawler."""
        return None
