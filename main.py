from scrape_all import WebsiteCrawler
from agentic_extractor import extract


if __name__ == "__main__":
    # Configuration
    website_url = "https://www.yangskitchenla.com/"  # Change this to your target website
    output_file = "website_content"      # Base name for output files
    delay = 1.0                         # Delay between requests in seconds
    use_selenium = False                # Whether to use Selenium
    max_pages = None                    # Maximum pages to crawl (None for no limit)
    
    # Create and run crawler
    crawler = WebsiteCrawler(
        base_url=website_url,
        output_file=output_file,
        delay=delay,
        use_selenium=use_selenium,
        max_pages=max_pages
    )
    
    try:
        crawler.crawl()
    except KeyboardInterrupt:
        print("\nCrawling interrupted by user. Saving progress...")
    finally:
        crawler.cleanup()
        print("Crawling completed. Output files saved.")

    extract("website_content.json")