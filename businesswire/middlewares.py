import json
import logging
import os
import time
from datetime import datetime, timezone

from scrapy import signals
from scrapy.http import HtmlResponse, Request, Response, TextResponse

logger = logging.getLogger(__name__)

HAR_DIR = os.path.join("output", "har")


class ScrappeyDownloaderMiddleware:
    """Downloader middleware that routes requests through the Scrappey API.

    Requests must have meta={'api': 'scrappey'} to be routed through Scrappey.
    All other requests pass through unchanged.

    When HAR_DEBUG=True in settings, saves a HAR file with the full raw
    Scrappey response for every request to output/har/.
    """

    def __init__(self, api_key, har_debug):
        self.api_key = api_key
        self.reuse_session = True
        self._session = None
        self.har_debug = har_debug
        self.har_entries = []

    @classmethod
    def from_crawler(cls, crawler):
        api_key = crawler.settings.get("SCRAPPEY_API_KEY", "")
        har_debug = crawler.settings.getbool("HAR_DEBUG", False)
        if not api_key:
            logger.warning(
                "SCRAPPEY_API_KEY not set — Scrappey middleware will fail. "
                "Set the SCRAPPEY_API_KEY environment variable."
            )
        middleware = cls(api_key, har_debug)
        crawler.signals.connect(middleware.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(middleware.spider_closed, signal=signals.spider_closed)
        return middleware

    def spider_opened(self, spider):
        if self.har_debug:
            os.makedirs(HAR_DIR, exist_ok=True)
            logger.info("[HAR] Debug logging enabled — saving to %s/", HAR_DIR)

    def spider_closed(self, spider):
        self._session = None
        self._save_har()

    # ------------------------------------------------------------------
    # Middleware hooks
    # ------------------------------------------------------------------

    def process_request(self, request):
        """Rewrite the request to POST to the Scrappey API."""
        if request.meta.get("proxied"):
            return None
        if request.meta.get("api") != "scrappey":
            return None

        request.meta["_har_start"] = time.time()
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

        original_url = request.meta.get("original_url", "unknown")

        if response.status == 400:
            logger.error("[Scrappey] Proxy returned 400 for %s", original_url)
            self._log_har_entry(request, response, {}, "proxy_400")
            return response

        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as exc:
            logger.warning("[Scrappey] Non-JSON response for %s: %s", original_url, exc)
            self._log_har_entry(request, response, {}, f"json_error: {exc}")
            return response.replace(status=400)

        if data.get("error"):
            logger.warning("[Scrappey] API error: %s", data["error"])
            self._log_har_entry(request, response, data, f"api_error: {data['error']}")
            return response.replace(status=400)

        solution = data.get("solution", {})
        status_code = solution.get("statusCode", 200)

        # Log HAR entry BEFORE transforming — this is the raw Scrappey response
        self._log_har_entry(request, response, data)

        if status_code >= 400:
            logger.warning("[Scrappey] HTTP %d for %s", status_code, original_url)
            return response.replace(status=status_code)

        # Reuse session across requests
        session_id = data.get("session", "")
        if self.reuse_session and session_id:
            self._session = session_id

        return self._build_response(request, solution, session_id)

    # ------------------------------------------------------------------
    # HAR debug logging
    # ------------------------------------------------------------------

    def _log_har_entry(self, request, response, scrappey_data, error=None):
        """Capture a HAR entry from the raw Scrappey response."""
        if not self.har_debug:
            return

        original_url = request.meta.get("original_url", request.url)
        started = request.meta.get("_har_start", time.time())
        elapsed_ms = round((time.time() - started) * 1000)

        solution = scrappey_data.get("solution", {})
        response_body = solution.get("response", "")
        inner_text = solution.get("innerText", "")

        entry = {
            "startedDateTime": datetime.now(timezone.utc).isoformat(),
            "time": elapsed_ms,
            "request": {
                "method": "GET",
                "url": original_url,
                "headers": [],
                "queryString": [],
                "bodySize": -1,
                "_scrappey": {
                    "session_sent": request.meta.get("scrappey_session", ""),
                    "cmd": "request.get",
                },
            },
            "response": {
                "status": solution.get("statusCode", response.status),
                "statusText": error or "",
                "headers": [
                    {"name": k, "value": v}
                    for k, v in (solution.get("responseHeaders") or {}).items()
                ],
                "cookies": solution.get("cookies", []),
                "content": {
                    "size": len(response_body),
                    "mimeType": (solution.get("responseHeaders") or {}).get(
                        "content-type", "text/html"
                    ),
                    "text": response_body,
                },
                "_scrappey": {
                    "currentUrl": solution.get("currentUrl", ""),
                    "verified": solution.get("verified", False),
                    "userAgent": solution.get("userAgent", ""),
                    "innerText": inner_text,
                    "innerTextLength": len(inner_text),
                    "responseLength": len(response_body),
                    "session": scrappey_data.get("session", ""),
                    "timeElapsed": scrappey_data.get("timeElapsed", 0),
                    "error": error or scrappey_data.get("error"),
                },
            },
        }

        self.har_entries.append(entry)

    def _save_har(self):
        """Write collected HAR entries to disk."""
        if not self.har_debug or not self.har_entries:
            return

        har = {
            "log": {
                "version": "1.2",
                "creator": {"name": "businesswire-scrapy-scrappey", "version": "1.0"},
                "entries": self.har_entries,
            }
        }

        filename = f"har_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.har"
        filepath = os.path.join(HAR_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(har, f, indent=2, ensure_ascii=False, default=str)

        logger.info("[HAR] Saved %d entries to %s", len(self.har_entries), filepath)

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
