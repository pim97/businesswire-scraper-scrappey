class BusinessWirePipeline:
    """Default item pipeline — items pass through unchanged.

    Add custom processing here if needed (e.g. deduplication, DB storage).
    """

    def process_item(self, item, spider):
        return item
