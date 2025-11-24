"""
Simple rate limiter for web crawling.
"""
import asyncio
from datetime import datetime, timedelta
from collections import deque
from typing import Dict
from dataclasses import dataclass


@dataclass
class RateLimitConfig:
    """Rate limit configuration for a domain."""
    
    requests_per_second: float = 0.5  # 1 request per 2 seconds
    max_concurrent: int = 2  # Max parallel requests to same domain


class DomainRateLimiter:
    """Rate limiter for a single domain."""
    
    def __init__(self, config: RateLimitConfig) -> None:
        self.config = config
        self.last_request: datetime | None = None
        self.semaphore = asyncio.Semaphore(config.max_concurrent)
    
    async def acquire(self) -> None:
        """Acquire permission to make a request."""
        await self.semaphore.acquire()
        
        # Enforce per-second rate limit
        if self.last_request:
            time_since_last = (datetime.now() - self.last_request).total_seconds()
            min_interval = 1.0 / self.config.requests_per_second
            
            if time_since_last < min_interval:
                wait_time = min_interval - time_since_last
                await asyncio.sleep(wait_time)
        
        self.last_request = datetime.now()
    
    def release(self) -> None:
        """Release the semaphore."""
        self.semaphore.release()


class GlobalRateLimiter:
    """Manages rate limiters for all domains."""
    
    def __init__(self) -> None:
        self.limiters: Dict[str, DomainRateLimiter] = {}
        
        # Domain-specific configs
        self.configs: Dict[str, RateLimitConfig] = {
            'sephora.com': RateLimitConfig(requests_per_second=0.5, max_concurrent=2),
            'ulta.com': RateLimitConfig(requests_per_second=1.0, max_concurrent=2),
            'google.com': RateLimitConfig(requests_per_second=0.2, max_concurrent=1),
        }
    
    def get_limiter(self, domain: str) -> DomainRateLimiter:
        """Get or create rate limiter for domain."""
        if domain not in self.limiters:
            config = self.configs.get(domain, RateLimitConfig())
            self.limiters[domain] = DomainRateLimiter(config)
        return self.limiters[domain]


# Global instance
rate_limiter = GlobalRateLimiter()
