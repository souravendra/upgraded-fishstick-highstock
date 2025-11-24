"""
Web crawlers for beauty product retailers.
"""
from app.crawlers.base import BaseCrawler, CrawlResult
from app.crawlers.sephora import SephoraCrawler
from app.crawlers.google_shopping import GoogleShoppingCrawler
from app.crawlers.upc_database import UPCDatabaseCrawler
from app.crawlers.manager import CrawlerManager

__all__ = [
    'BaseCrawler',
    'CrawlResult',
    'SephoraCrawler',
    'GoogleShoppingCrawler',
    'UPCDatabaseCrawler',
    'CrawlerManager',
]
