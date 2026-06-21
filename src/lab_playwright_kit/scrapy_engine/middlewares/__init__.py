"""Scrapy Middlewares — stealth, playwright, антидетект, proxy rotation."""

from .playwright_middleware import PlaywrightMiddleware
from .proxy_middleware import ProxyMiddleware
from .stealth_middleware import StealthMiddleware


__all__ = [
    "StealthMiddleware",
    "PlaywrightMiddleware",
    "ProxyMiddleware",
]
