import json
import logging

from scrapy import signals
from scrapy.http import HtmlResponse, Request, Response, TextResponse

logger = logging.getLogger(__name__)


class ScrappeyDownloaderMiddleware:
    """Downloader middleware that routes requests through the Scrappey API.

    Requests must have meta={'api': 'scrappey'} to be routed through Scrappey.
    All other requests pass through unchanged.
    """

    def __init__(self, api_key):
        self.api_key = api_key
        self.reuse_session = True
        self._session = None

    @classmethod
    def from_crawler(cls, crawler):
        api_key = crawler.settings.get("SCRAPPEY_API_KEY", "")
        if not api_key:
            logger.warning(
                "SCRAPPEY_API_KEY not set — Scrappey middleware will fail. "
                "Set the SCRAPPEY_API_KEY environment variable."
            )
        middleware = cls(api_key)
        crawler.signals.connect(middleware.spider_closed, signal=signals.spider_closed)
        return middleware

    def spider_closed(self, spider):
        self._session = None

    # ------------------------------------------------------------------
    # Middleware hooks
    # ------------------------------------------------------------------

    def process_request(self, request):
        """Rewrite the request to POST to the Scrappey API."""
        if request.meta.get("proxied"):
            return None
        if request.meta.get("api") != "scrappey":
            return None

        body = self._build_scrappey_body(request)
        scrappey_url = f"https://publisher.scrappey.com/api/v1?key={self.api_key}"

        return Request(
            url=scrappey_url,
            method="POST",
            headers={"Content-Type": "application/json"},
            body=json.dumps(body),
            callback=request.callback,
            errback=request.errback,
            dont_filter=True,
            cb_kwargs=request.cb_kwargs,
            priority=request.priority,
            meta={
                **request.meta,
                "proxied": True,
                "original_url": request.url,
            },
        )

    def process_response(self, request, response):
        """Unpack a Scrappey JSON response into a normal Scrapy response."""
        if request.meta.get("api") != "scrappey":
            return response

        if response.status == 400:
            logger.error(
                "[Scrappey] Proxy returned 400 for %s",
                request.meta.get("original_url", "unknown"),
            )
            return response

        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as exc:
            logger.warning(
                "[Scrappey] Non-JSON response for %s: %s",
                request.meta.get("original_url", "unknown"),
                exc,
            )
            return response.replace(status=400)

        if data.get("error"):
            logger.warning("[Scrappey] API error: %s", data["error"])
            return response.replace(status=400)

        solution = data.get("solution", {})
        status_code = solution.get("statusCode", 200)
        if status_code >= 400:
            logger.warning(
                "[Scrappey] HTTP %d for %s",
                status_code,
                request.meta.get("original_url", "unknown"),
            )
            return response.replace(status=status_code)

        # Reuse session across requests
        session_id = data.get("session", "")
        if self.reuse_session and session_id:
            self._session = session_id

        return self._build_response(request, solution, session_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_scrappey_body(self, request):
        """Construct the JSON body for the Scrappey API request."""
        cmd = "request.get" if request.method.upper() == "GET" else "request.post"

        body = {
            "cmd": cmd,
            "url": request.url,
        }

        if request.method.upper() == "POST" and request.body:
            body["postData"] = request.body.decode("utf-8", errors="replace")

        if request.headers:
            body["customHeaders"] = {
                k.decode(): v[0].decode()
                for k, v in request.headers.items()
                if v
            }

        # Prefer an explicit session from the caller, then fall back to stored one
        session_id = request.meta.get("scrappey_session") or (
            self._session if self.reuse_session else None
        )
        if session_id:
            body["session"] = session_id

        extra = request.meta.get("scrappey_options") or {}
        body.update(extra)

        return body

    @staticmethod
    def _build_response(request, solution, session_id):
        """Convert a Scrappey solution dict into a Scrapy Response."""
        html = solution.get("response") or solution.get("innerText") or ""
        current_url = solution.get("currentUrl") or request.meta.get("original_url", request.url)
        response_headers = solution.get("responseHeaders") or {}
        status = solution.get("statusCode", 200)

        # Forward cookies so Scrapy's cookie middleware can pick them up
        cookies = solution.get("cookies") or []
        if cookies:
            response_headers["Set-Cookie"] = "; ".join(
                f"{c['name']}={c['value']}" for c in cookies
            )

        # Update meta on the original request so the callback is preserved
        request.meta["scrappey_session"] = session_id
        request.meta["scrappey_inner_text"] = solution.get("innerText", "")

        response_cls = HtmlResponse if html.lstrip().startswith("<") else TextResponse

        return response_cls(
            url=current_url,
            status=status,
            headers=response_headers,
            body=html.encode("utf-8"),
            encoding="utf-8",
            request=request,
        )
