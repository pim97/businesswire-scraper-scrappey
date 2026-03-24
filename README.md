# BusinessWire Scraper — Scrapy + Scrappey

A [Scrapy](https://scrapy.org/) spider that scrapes press releases from [BusinessWire](https://www.businesswire.com/) using [Scrappey](https://scrappey.com/) to handle anti-bot protection (Akamai) and residential proxies.

Covers 7 industry categories and extracts structured data from each article.

## Industries

| ID        | Category        |
|-----------|-----------------|
| 1000039   | Automotive      |
| 1000146   | Biotechnology   |
| 1000088   | Pharmaceutical  |
| 1085811   | Life Sciences   |
| 1050070   | Oncology        |
| 1000045   | Health/Medical  |
| 1000123   | Technology      |

## Extracted Fields

Each article yields the following fields:

| Field          | Description                                  |
|----------------|----------------------------------------------|
| `publish_date` | ISO 8601 publication date                    |
| `title`        | Article headline                             |
| `summary`      | Short description from the listing page      |
| `tags`         | Category/topic tags                          |
| `full_text`    | Full article body text                       |
| `contact_info` | Press contact details                        |
| `company_name` | Issuing company name                         |
| `company_url`  | Company website URL                          |
| `url`          | Direct link to the article                   |
| `industry_id`  | BusinessWire industry category ID            |

## Prerequisites

- Python 3.10+
- A [Scrappey](https://scrappey.com/) API key

## Setup

1. Clone the repository:

```bash
git clone https://github.com/pim97/businesswire-scrapy-scrappey.git
cd businesswire-scrapy-scrappey
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure your API key:

```bash
cp .env.example .env
```

Edit `.env` and replace `your_api_key_here` with your Scrappey API key.

4. Set the environment variable:

```bash
# Linux / macOS
export SCRAPPEY_API_KEY=your_api_key_here

# Windows (PowerShell)
$env:SCRAPPEY_API_KEY="your_api_key_here"

# Windows (cmd)
set SCRAPPEY_API_KEY=your_api_key_here
```

## Usage

Run the spider:

```bash
scrapy crawl businesswire
```

Output is saved automatically to the `output/` folder as JSON.

To specify a custom output file:

```bash
scrapy crawl businesswire -o results.json
```

## How It Works

1. The spider requests each industry listing page through Scrappey
2. Parses the listing to extract article links, titles, summaries, and tags
3. Fetches each individual article page through Scrappey
4. Extracts all structured fields (date, full text, contacts, company info)
5. Outputs everything as structured JSON

### Scrappey Integration

All requests are routed through a custom Scrapy downloader middleware (`businesswire/middlewares.py`) that:

- Converts Scrapy requests into Scrappey API calls
- Handles session reuse across requests for efficiency
- Unpacks Scrappey responses back into standard Scrapy responses
- Preserves cookies and headers

Scrappey handles Akamai bot detection behind the scenes using residential proxies and real browser sessions.

## Configuration

All configuration is done via environment variables in your `.env` file:

| Variable           | Default | Description                                           |
|--------------------|---------|-------------------------------------------------------|
| `SCRAPPEY_API_KEY` | —       | Your Scrappey API key (required)                      |
| `SCRAPE_DEPTH`     | `10`    | Max articles to scrape per industry (`0` = unlimited) |
| `HAR_DEBUG`        | `false` | Save raw request/response data to `output/har/`       |

Additional settings in `businesswire/settings.py`:

| Setting                         | Default | Description                              |
|---------------------------------|---------|------------------------------------------|
| `CONCURRENT_REQUESTS`           | 3       | Max parallel requests (low to avoid 429s)|
| `DOWNLOAD_DELAY`                | 2       | Seconds between requests                 |
| `RETRY_TIMES`                   | 3       | Retry attempts on 400/429/500 errors     |
| `DOWNLOAD_TIMEOUT`              | 120     | Timeout per request (seconds)            |

## Project Structure

```
businesswire-scrapy-scrappey/
├── scrapy.cfg                          # Scrapy project config
├── requirements.txt                    # Python dependencies
├── .env.example                        # Environment variable template
├── .gitignore
├── README.md
└── businesswire/
    ├── __init__.py
    ├── settings.py                     # Scrapy settings + Scrappey config
    ├── items.py                        # ArticleItem definition
    ├── middlewares.py                  # Scrappey downloader middleware
    ├── pipelines.py                    # Item pipeline (extensible)
    └── spiders/
        ├── __init__.py
        └── industries.py              # Main spider
```

## Customization

### Adding or Changing Industries

Edit the `INDUSTRIES` list in `businesswire/spiders/industries.py`:

```python
INDUSTRIES = [
    1000039,  # Automotive
    1000146,  # Biotechnology
    # Add more industry IDs here...
]
```

You can find industry IDs from the BusinessWire newsroom URL parameter: `businesswire.com/newsroom?industry=<ID>`

### Adjusting Rate Limits

If you're seeing 429 (rate limited) errors, increase `DOWNLOAD_DELAY` or decrease `CONCURRENT_REQUESTS` in `businesswire/settings.py`.

## License

MIT
