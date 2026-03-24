import scrapy


class ArticleItem(scrapy.Item):
    publish_date = scrapy.Field()
    title = scrapy.Field()
    summary = scrapy.Field()
    tags = scrapy.Field()
    full_text = scrapy.Field()
    contact_info = scrapy.Field()
    company_name = scrapy.Field()
    company_url = scrapy.Field()
    url = scrapy.Field()
    industry_id = scrapy.Field()
