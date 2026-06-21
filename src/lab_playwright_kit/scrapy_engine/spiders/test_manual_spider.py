from scrapy import Request, Spider


class TestSpider(Spider):
    name = "test_manual"
    allowed_domains = ["example.com"]

    def start_requests(self):
        yield Request(
            "https://example.com",
            meta={"playwright": True, "playwright_include_page": True},
            callback=self.parse,
        )

    def parse(self, response):
        print(f"RESPONSE: {response.status} {response.url}")
        yield {"status": response.status, "url": response.url}

    def closed(self, reason):
        print(f"SPIDER CLOSED: {reason}")
