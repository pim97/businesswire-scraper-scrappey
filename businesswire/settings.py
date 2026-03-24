import os

BOT_NAME = "businesswire"

SPIDER_MODULES = ["businesswire.spiders"]
NEWSPIDER_MODULE = "businesswire.spiders"

# Scrappey API key — set via environment variable
SCRAPPEY_API_KEY = os.environ.get("SCRAPPEY_API_KEY", "")

# Crawl responsibly
ROBOTSTXT_OBEY = False  # We go through Scrappey, not direct

# Concurrency — keep low to avoid 429s from BusinessWire
CONCURRENT_REQUESTS = 3
DOWNLOAD_DELAY = 2
CONCURRENT_REQUESTS_PER_DOMAIN = 3

# Retry settings
RETRY_TIMES = 3
RETRY_HTTP_CODES = [400, 429, 500, 502, 503]

# Timeout (Scrappey can be slow due to browser rendering)
DOWNLOAD_TIMEOUT = 120

# Middlewares
DOWNLOADER_MIDDLEWARES = {
    # Disable middlewares that conflict with Scrappey
    "scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware": None,
    "scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware": None,
    # Enable Scrappey middleware
    "businesswire.middlewares.ScrappeyDownloaderMiddleware": 543,
}

# Output
FEEDS = {
    "output/%(name)s_%(time)s.json": {
        "format": "json",
        "encoding": "utf-8",
        "indent": 2,
        "overwrite": True,
    },
}

# Logging
LOG_LEVEL = "INFO"

# Disable telnet console
TELNETCONSOLE_ENABLED = False

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
