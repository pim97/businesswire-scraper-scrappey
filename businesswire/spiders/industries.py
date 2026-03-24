import json
import re

import scrapy
from scrapy.selector import Selector

from businesswire.items import ArticleItem

# BusinessWire industry category IDs
INDUSTRIES = [
    1000039,  # Automotive
    1000146,  # Biotechnology
    1000088,  # Pharmaceutical
    1085811,  # Life Sciences
    1050070,  # Oncology
    1000045,  # Health/Medical
    1000123,  # Technology
]

BASE_URL = "https://www.businesswire.com"


class BusinessWireSpider(scrapy.Spider):
    name = "businesswire"
    allowed_domains = ["businesswire.com"]

    async def start(self):
        for industry_id in INDUSTRIES:
            url = f"{BASE_URL}/newsroom?industry={industry_id}"
            yield scrapy.Request(
                url=url,
                callback=self.parse_listing,
                meta={"api": "scrappey", "industry_id": industry_id},
                dont_filter=True,
            )

    def parse_listing(self, response):
        """Extract article links from an industry listing page."""
        industry_id = response.meta["industry_id"]
        sel = Selector(response)

        depth = self.settings.getint("SCRAPE_DEPTH", 10)
        links = sel.css('a[href^="/news/home/"]')
        if depth > 0:
            links = links[:depth]
        self.logger.info(
            "[Industry %d] Found %d article links", industry_id, len(links)
        )

        for link in links:
            href = link.attrib.get("href", "")
            if not href:
                continue

            title = link.css("h2::text").get("").strip()
            if not title:
                continue

            # Walk up to the card container for summary and tags
            card = link.xpath("ancestor::div[contains(@class, 'relative')][1]")
            summary = ""
            if card:
                # Look for line-clamp div
                summary_parts = card.css("[class*='line-clamp']::text").getall()
                summary = " ".join(p.strip() for p in summary_parts if p.strip())

            tags = []
            if card:
                for btn in card.css("button::text").getall():
                    tag = btn.strip()
                    if tag:
                        tags.append(tag)

            article_url = f"{BASE_URL}{href}"

            yield scrapy.Request(
                url=article_url,
                callback=self.parse_article,
                meta={
                    "api": "scrappey",
                    "industry_id": industry_id,
                    "listing_title": title,
                    "listing_summary": summary,
                    "listing_tags": tags,
                },
                dont_filter=True,
            )

    def parse_article(self, response):
        """Extract all fields from an article page."""
        sel = Selector(response)
        meta = response.meta
        inner_text = meta.get("scrappey_inner_text", "")

        item = ArticleItem()
        item["url"] = meta.get("original_url", response.url)
        item["industry_id"] = meta["industry_id"]
        item["title"] = meta["listing_title"]
        item["summary"] = meta["listing_summary"]
        item["tags"] = meta["listing_tags"]

        # --- Publish date ---
        item["publish_date"] = self._extract_publish_date(sel)

        # --- Full text ---
        item["full_text"] = self._extract_full_text(sel, inner_text)

        # --- Contact info ---
        item["contact_info"] = self._extract_contact_info(sel)

        # --- Company name ---
        item["company_name"] = self._extract_company_name(sel)

        # --- Company URL ---
        item["company_url"] = self._extract_company_url(sel)

        if not item["full_text"]:
            self.logger.warning(
                "Empty full_text for: %s", item["title"][:60]
            )

        yield item

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    def _extract_publish_date(self, sel):
        """Extract publish date from JSON-LD or fallback selectors."""
        # Try JSON-LD structured data first
        for script in sel.css('script[type="application/ld+json"]::text').getall():
            try:
                data = json.loads(script)
                if isinstance(data, dict) and data.get("datePublished"):
                    return data["datePublished"]
            except (json.JSONDecodeError, TypeError):
                continue

        # Fallback: client-rendered date div
        date_text = sel.css("div.ui-kit-press-release__date::text").get("").strip()
        if date_text and date_text != "-":
            return date_text

        return ""

    def _extract_full_text(self, sel, inner_text):
        """Extract article full text from various selectors."""
        # Primary: #bw-release-story
        story = sel.css("#bw-release-story").get("")
        if story:
            return self._html_to_text(story)

        # Fallbacks
        for selector in [".bw-release-story", "article .rich-text", "article"]:
            el = sel.css(selector).get("")
            if el:
                return self._html_to_text(el)

        # Last resort: innerText from Scrappey
        if inner_text:
            return inner_text.strip()

        return ""

    def _extract_contact_info(self, sel):
        """Extract contact information."""
        container = sel.css("div.ui-kit-press-release-contacts")
        if not container:
            return ""

        # Try specific contact div first
        contact_div = container.css('div[id^="bw-release-contact"]')
        if contact_div:
            texts = contact_div.css("::text").getall()
            return " ".join(t.strip() for t in texts if t.strip())

        # Fallback: grab everything after "Contacts" heading
        texts = container.css("::text").getall()
        full = " ".join(t.strip() for t in texts if t.strip())
        return re.sub(r"^Contacts\s*", "", full, flags=re.IGNORECASE).strip()

    def _extract_company_name(self, sel):
        """Extract company name from sidebar or 'More News From' section."""
        name = sel.css("h3.ui-kit-press-release-sidebar__company::text").get("").strip()
        if name:
            return name

        # Fallback: "More News From X"
        for div in sel.css("div::text").getall():
            text = div.strip()
            if text.startswith("More News From "):
                return text.replace("More News From ", "").strip()

        return ""

    def _extract_company_url(self, sel):
        """Extract company URL from sidebar logo link."""
        url = sel.css("div.ui-kit-press-release-sidebar__logo a::attr(href)").get("")
        if url:
            return url

        # Fallback: any link wrapping a logo image (case-insensitive via XPath)
        for link in sel.css("a[href]"):
            if link.xpath('.//img[contains(translate(@alt, "LOGO", "logo"), "logo")]'):
                return link.attrib.get("href", "")

        return ""

    @staticmethod
    def _html_to_text(html):
        """Convert HTML to clean text (simple approach without external deps)."""
        sel = Selector(text=html)
        texts = sel.css("::text").getall()
        return "\n".join(t.strip() for t in texts if t.strip())
