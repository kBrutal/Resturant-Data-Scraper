#!/usr/bin/env python3
"""
Website Crawler and Content Extractor
------------------------------------
This script crawls a website by following all links within the same domain,
extracts text content from each page, and saves the results to JSON and TXT files.

Requirements:
- Python 3.6+
- requests
- beautifulsoup4
- selenium
- webdriver-manager
"""

import argparse
import json
import os
import time
import urllib.parse
from collections import defaultdict
import re
import logging
import datetime

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException


class WebsiteCrawler:
    def __init__(self, base_url, output_file="website_content", delay=1.0, use_selenium=False, max_pages=None):
        """Initialize the crawler with the target website URL."""
        self.base_url = base_url
        self.output_json = f"{output_file}.json"
        self.output_txt = f"{output_file}.txt"
        self.domain = urllib.parse.urlparse(base_url).netloc
        self.delay = delay
        self.use_selenium = use_selenium
        self.max_pages = max_pages
        
        # Setup logging
        self._setup_logging()
        
        # Track visited URLs to avoid duplicates
        self.visited_urls = set()
        
        # Store extracted content
        self.content = defaultdict(dict)
        
        # Initialize session for consistent cookies
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        self.logger.info(f"Initialized crawler for domain: {self.domain}")
        self.logger.info(f"Output JSON file: {self.output_json}")
        self.logger.info(f"Output TXT file: {self.output_txt}")
        self.logger.info(f"Request delay: {self.delay} seconds")
        self.logger.info(f"Using Selenium: {self.use_selenium}")
        if self.max_pages:
            self.logger.info(f"Maximum pages to crawl: {self.max_pages}")
        
        # Initialize Selenium if required
        self.driver = None
        if self.use_selenium:
            self._setup_selenium()
            
    def _setup_logging(self):
        """Set up logging configuration."""
        # Create a timestamp for the log file
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = f"crawler_{timestamp}.log"
        
        # Configure logging
        self.logger = logging.getLogger("WebsiteCrawler")
        self.logger.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_format)
        
        # File handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_format)
        
        # Add handlers
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
        
        print(f"Logging to: {log_file}")
        self.logger.info(f"Starting web crawler session at {timestamp}")
    
    def _setup_selenium(self):
        """Set up the Selenium WebDriver."""
        self.logger.info("Setting up Selenium WebDriver...")
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run in headless mode
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument(f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.logger.info("Selenium WebDriver initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Selenium WebDriver: {e}")
            raise
    
    def is_valid_url(self, url):
        """Check if URL is valid and belongs to the same domain."""
        if not url:
            return False
        
        # Skip URLs with fragments or parameters for simplicity
        if '#' in url:
            url = url.split('#')[0]
        
        # Convert relative URLs to absolute URLs
        if url.startswith('/'):
            url = urllib.parse.urljoin(self.base_url, url)
        
        # Parse the URL
        parsed_url = urllib.parse.urlparse(url)
        
        # Check if URL belongs to the same domain
        if parsed_url.netloc and parsed_url.netloc != self.domain:
            self.logger.debug(f"Skipping external domain URL: {url}")
            return False
        
        # Skip non-HTTP(S) URLs
        if parsed_url.scheme not in ('http', 'https', ''):
            self.logger.debug(f"Skipping non-HTTP URL: {url}")
            return False
        
        # Skip common non-HTML resources
        extensions_to_skip = ('.pdf', '.jpg', '.jpeg', '.png', '.gif', '.css', '.js', '.xml', 
                            '.mp3', '.mp4', '.zip', '.tar.gz', '.doc', '.docx', '.xls', '.xlsx')
        if any(parsed_url.path.endswith(ext) for ext in extensions_to_skip):
            self.logger.debug(f"Skipping non-HTML resource: {url}")
            return False
        
        return True
    
    def normalize_url(self, url):
        """Normalize URL by converting relative to absolute and handling edge cases."""
        if not url:
            return None
        
        # Remove URL fragments
        if '#' in url:
            url = url.split('#')[0]
        
        # Convert relative URLs to absolute
        if not url.startswith(('http://', 'https://')):
            url = urllib.parse.urljoin(self.base_url, url)
        
        return url
    
    def extract_content_with_requests(self, url):
        """Extract content from a URL using requests and BeautifulSoup."""
        try:
            self.logger.info(f"Fetching content with requests: {url}")
            start_time = time.time()
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            elapsed_time = time.time() - start_time
            self.logger.info(f"Fetched {url} in {elapsed_time:.2f} seconds (Status: {response.status_code})")
            
            # Log page size
            content_length = len(response.content)
            self.logger.info(f"Page size: {content_length/1024:.2f} KB")
            
            # Parse HTML content
            self.logger.debug(f"Parsing HTML content from {url}")
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract text and remove excessive whitespace
            content = self._extract_text_from_soup(soup)
            content_length = len(content)
            self.logger.info(f"Extracted {content_length} characters of text")
            
            # Extract links
            links = self._extract_links_from_soup(soup, url)
            self.logger.info(f"Found {len(links)} links on page")
            
            return content, links
        
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {url}: {e}")
            return None, []
    
    def extract_content_with_selenium(self, url):
        """Extract content from a URL using Selenium for JavaScript rendering."""
        try:
            self.logger.info(f"Fetching content with Selenium: {url}")
            start_time = time.time()
            
            self.driver.get(url)
            self.logger.debug(f"Waiting for page to load: {url}")
            
            # Wait for page to load (adjust timeout as needed)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Allow additional time for JavaScript to execute
            self.logger.debug(f"Waiting for JS execution: {url}")
            time.sleep(2)
            
            elapsed_time = time.time() - start_time
            self.logger.info(f"Loaded {url} with Selenium in {elapsed_time:.2f} seconds")
            
            # Get page size
            page_size = len(self.driver.page_source)
            self.logger.info(f"Page size after JS rendering: {page_size/1024:.2f} KB")
            
            # Get the page source after JS execution
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # Extract text
            content = self._extract_text_from_soup(soup)
            content_length = len(content)
            self.logger.info(f"Extracted {content_length} characters of text")
            
            # Extract links
            links = self._extract_links_from_soup(soup, url)
            self.logger.info(f"Found {len(links)} links on page after JS rendering")
            
            return content, links
        
        except (TimeoutException, WebDriverException) as e:
            self.logger.error(f"Error loading {url} with Selenium: {e}")
            return None, []
    
    def _extract_text_from_soup(self, soup):
        """Extract and clean text content from BeautifulSoup object."""
        # Remove script and style elements
        for element in soup(['script', 'style', 'meta', 'noscript']):
            element.extract()
        
        # Get text
        text = soup.get_text(separator=' ', strip=True)
        
        # Clean up text - replace multiple spaces and newlines with single space
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def _extract_links_from_soup(self, soup, current_url):
        """Extract valid links from BeautifulSoup object."""
        links = []
        total_links = 0
        valid_links = 0
        
        # Extract all anchor tags
        for a_tag in soup.find_all('a', href=True):
            total_links += 1
            href = a_tag.get('href', '').strip()
            
            # Validate and normalize URL
            normalized_url = self.normalize_url(href)
            if normalized_url and self.is_valid_url(normalized_url):
                links.append(normalized_url)
                valid_links += 1
                self.logger.debug(f"Found valid link: {normalized_url}")
        
        self.logger.debug(f"Extracted {valid_links} valid links out of {total_links} total links")
        return links
    
    def crawl(self):
        """Start crawling the website from the base URL."""
        # Add base URL to the queue
        queue = [self.base_url]
        
        self.logger.info(f"Starting crawl from: {self.base_url}")
        start_time = time.time()
        page_count = 0
        
        while queue and (self.max_pages is None or page_count < self.max_pages):
            # Get the next URL to process
            url = queue.pop(0)
            
            # Skip if already visited
            if url in self.visited_urls:
                self.logger.debug(f"Skipping already visited URL: {url}")
                continue
            
            # Log progress
            remaining = len(queue)
            self.logger.info(f"[{page_count+1}] Processing: {url} (Queue size: {remaining})")
            
            # Mark as visited
            self.visited_urls.add(url)
            page_count += 1
            
            # Extract content based on the method
            if self.use_selenium:
                content, links = self.extract_content_with_selenium(url)
            else:
                content, links = self.extract_content_with_requests(url)
            
            # Store content if extraction successful
            if content:
                # Normalize URL for storage (remove trailing slash for consistency)
                normalized_url = url.rstrip('/')
                title = self._extract_title(url)
                self.content[normalized_url] = {
                    'title': title,
                    'text': content
                }
                self.logger.info(f"Stored content for '{title}' page ({len(content)} chars)")
            else:
                self.logger.warning(f"No content extracted from {url}")
            
            # Add new unvisited links to the queue
            new_links = 0
            for link in links:
                if link not in self.visited_urls and link not in queue:
                    queue.append(link)
                    new_links += 1
            
            self.logger.info(f"Added {new_links} new links to the queue")
            
            # Respect robots.txt delay
            if self.delay > 0:
                self.logger.debug(f"Waiting {self.delay} seconds before next request")
                time.sleep(self.delay)
            
            # Periodically save progress to avoid losing data on long crawls
            if page_count % 10 == 0:
                self.save_content()
                elapsed = time.time() - start_time
                avg_time_per_page = elapsed / page_count if page_count > 0 else 0
                self.logger.info(f"Progress saved: {page_count} pages crawled in {elapsed:.2f} seconds")
                self.logger.info(f"Average time per page: {avg_time_per_page:.2f} seconds")
                self.logger.info(f"Remaining queue size: {len(queue)} URLs")
        
        # Final save
        self.save_content()
        total_time = time.time() - start_time
        
        # Log crawl statistics
        self.logger.info("=" * 50)
        self.logger.info(f"Crawling complete. Processed {page_count} pages.")
        self.logger.info(f"Total crawl time: {total_time:.2f} seconds")
        self.logger.info(f"Average time per page: {total_time/page_count if page_count > 0 else 0:.2f} seconds")
        self.logger.info(f"Total unique URLs visited: {len(self.visited_urls)}")
        self.logger.info(f"Content extracted from {len(self.content)} pages")
        self.logger.info(f"Content saved to: {self.output_json} and {self.output_txt}")
        self.logger.info("=" * 50)
    
    def _extract_title(self, url):
        """Extract page title based on URL."""
        # Parse URL to get path
        path = urllib.parse.urlparse(url).path
        
        # Use last path segment as title, or 'Home' if root
        if not path or path == '/':
            return 'Home'
        
        # Remove trailing slash and extract last segment
        path = path.rstrip('/')
        title = os.path.basename(path)
        
        # Clean up and title-case
        title = title.replace('-', ' ').replace('_', ' ').title()
        
        return title
    
    def save_content(self):
        """Save extracted content to JSON and TXT files."""
        # Save to JSON
        with open(self.output_json, 'w', encoding='utf-8') as f:
            json.dump(self.content, f, indent=2, ensure_ascii=False)
        
        # Save to TXT
        with open(self.output_txt, 'w', encoding='utf-8') as f:
            for url, data in self.content.items():
                f.write(f"URL: {url}\n")
                f.write(f"Title: {data['title']}\n")
                f.write("-" * 80 + "\n")
                f.write(data['text'] + "\n")
                f.write("=" * 80 + "\n\n")
    
    def cleanup(self):
        """Clean up resources."""
        if self.driver:
            self.driver.quit()


def crawl():
    parser = argparse.ArgumentParser(description='Crawl a website and extract content')
    parser.add_argument('url', help='Base URL of the website to crawl')
    parser.add_argument('--output', '-o', default='website_content', help='Output file base name (without extension)')
    parser.add_argument('--delay', '-d', type=float, default=1.0, help='Delay between requests in seconds')
    parser.add_argument('--selenium', '-s', action='store_true', help='Use Selenium for JavaScript rendered content')
    parser.add_argument('--max-pages', '-m', type=int, help='Maximum number of pages to crawl')
    
    args = parser.parse_args()
    
    crawler = WebsiteCrawler(
        base_url=args.url,
        output_file=args.output,
        delay=args.delay,
        use_selenium=args.selenium,
        max_pages=args.max_pages
    )
    
    try:
        crawler.crawl()
    finally:
        crawler.cleanup()

