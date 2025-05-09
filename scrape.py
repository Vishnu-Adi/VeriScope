# FILE: scrape.py
import ast
import newspaper as n3k
import sys
import concurrent.futures
import logging
import json
from datetime import datetime, timezone

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
MIN_ARTICLE_TEXT_LENGTH = 500
MIN_ARTICLE_TITLE_LENGTH = 10
MIN_GENERATED_SUMMARY_LENGTH = 30
NON_ARTICLE_TITLE_KEYWORDS = [
    "news", "politics", "world", "media", "video", "topic", "section",
    "edition", "menu", "live", "update", "gallery", "photo", "podcast",
    "newsletter", "subscribe", "about", "contact", "terms", "privacy",
    "login", "register", "profile", "author", "contributor", "search",
    "tag", "category", "index", "archive", "sitemap", "rss", "feed",
    "shop", "store", "careers", "jobs", "press", "advertising", "events"
]
URL_SKIP_PATTERNS = ["/video/", "/gallery/", "/live/", "/topic/", "/section/", "/author/", "/profile/"]
MAX_WORKERS = 10 # Adjust based on your system/network
REQUEST_TIMEOUT = 15 # Seconds for article download

def format_article(url_info):
    """
    Downloads, parses, and validates a single article URL.
    url_info is expected to be a list like ['http://example.com/article', 'brand']
    Returns a dictionary with article data if valid, otherwise None.
    """
    if not isinstance(url_info, list) or len(url_info) != 2:
        logging.warning(f"Skipping invalid url_info format: {url_info}")
        return None

    url, brand = url_info[0], url_info[1]
    logging.debug(f"Attempting to process URL: {url}")

    if any(pattern in url for pattern in URL_SKIP_PATTERNS):
        logging.info(f"Skipping URL based on skip pattern: {url}")
        return None

    try:
        article = n3k.Article(url, language="en", fetch_images=True, request_timeout=REQUEST_TIMEOUT)
        article.download()

        if not article.html or len(article.html) < 1500:
             logging.warning(f"Skipping URL (likely redirect or minimal content): {url}")
             return None

        article.parse()

        # --- Validation Checks ---
        if not article.title or len(article.title) < MIN_ARTICLE_TITLE_LENGTH:
            logging.warning(f"Skipping article (title too short or missing): {url}")
            return None
        title_lower = article.title.lower()
        # Check if the title *is* exactly one of the keywords or starts/ends with it broadly
        is_non_article_title = False
        for keyword in NON_ARTICLE_TITLE_KEYWORDS:
            kw_lower = keyword.lower()
            if title_lower == kw_lower or \
               title_lower.startswith(kw_lower + ' ') or \
               title_lower.startswith(kw_lower + ':') or \
               title_lower.endswith(' ' + kw_lower):
                is_non_article_title = True
                break
        if is_non_article_title:
             logging.warning(f"Skipping article (likely category/non-article based on title keywords): '{article.title}' ({url})")
             return None

        if not article.text or len(article.text) < MIN_ARTICLE_TEXT_LENGTH:
            logging.warning(f"Skipping article (text too short: {len(article.text)} chars): '{article.title}' ({url})")
            return None

        text_lower = article.text.lower()
        if " ad " in text_lower or " advertisement " in text_lower or "sponsored content" in text_lower:
            logging.info(f"Skipping article (detected as ad/sponsored): '{article.title}' ({url})")
            return None

        # --- NLP (Optional) ---
        summary = ""
        keywords = []
        try:
            article.nlp()
            if article.summary and len(article.summary) >= MIN_GENERATED_SUMMARY_LENGTH:
                summary = article.summary
            if article.keywords:
                keywords = article.keywords
        except Exception as nlp_err:
            logging.warning(f"NLP step failed for '{article.title}' ({url}): {nlp_err}. Proceeding without summary/keywords.")

        # --- Date Formatting ---
        publish_date_iso = None
        if article.publish_date:
            try:
                publish_date_aware = article.publish_date.replace(tzinfo=timezone.utc) if article.publish_date.tzinfo is None else article.publish_date
                publish_date_iso = publish_date_aware.isoformat()
            except Exception as date_err:
                logging.warning(f"Could not format publish_date '{article.publish_date}' for {url}: {date_err}")

        logging.info(f"Successfully parsed: '{article.title}' ({url})")
        return {
            "url": url,
            "text": article.text,
            "title": article.title,
            "authors": list(article.authors) if article.authors else [],
            "publish_date": publish_date_iso, # Store as ISO string or None
            "top_image": article.top_image,
            "images": list(article.images) if article.images else [],
            "movies": list(article.movies) if article.movies else [],
            "keywords": keywords,
            "summary": summary, # Store newspaper3k summary (or empty string)
            "brand": brand,
        }

    except n3k.article.ArticleException as e:
        logging.warning(f"Newspaper3k ArticleException for {url}: {e}")
        return None
    except Exception as e:
        logging.error(f"General failure processing {url}: {e}", exc_info=False)
        return None

def process_and_save_articles(articles_data):
    """ Saves the list of valid article dictionaries to articles.json """
    output_path = "articles.json"
    if not articles_data:
        logging.warning("No valid articles found to process.")
        try:
            with open(output_path, "w", encoding='utf-8') as f:
                json.dump([], f)
            logging.info(f"Created empty {output_path} as no valid articles were found.")
        except IOError as e:
            logging.error(f"Failed to write empty {output_path}: {e}")
        return

    logging.info(f"Saving {len(articles_data)} valid articles to {output_path}")
    try:
        with open(output_path, "w", encoding='utf-8') as f:
            json.dump(articles_data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        logging.error(f"Failed to write {output_path}: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while writing {output_path}: {e}")

if __name__ == "__main__":
    logging.info("Starting article scraping process...")
    links_file = "links.txt"
    try:
        with open(links_file, "r", encoding='utf-8') as f:
            urls_to_process = [ast.literal_eval(line.strip()) for line in f]
            n_urls = len(urls_to_process)
            logging.info(f"Read {n_urls} URLs from {links_file}")
    except FileNotFoundError:
        logging.error(f"{links_file} not found. Please generate it first.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error reading or parsing {links_file}: {e}")
        sys.exit(1)

    if not urls_to_process:
        logging.warning("No URLs found in links.txt. Exiting.")
        sys.exit(0)

    logging.info("Starting article download and parsing...")
    formatted_articles = []
    processed_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(format_article, url_info): url_info for url_info in urls_to_process}
        for future in concurrent.futures.as_completed(future_to_url):
            url_info = future_to_url[future]
            processed_count += 1
            try:
                result = future.result()
                if result is not None:
                    formatted_articles.append(result)
            except Exception as exc:
                logging.error(f"URL {url_info[0]} generated an exception in future processing: {exc}")

            if processed_count % 50 == 0 or processed_count == n_urls:
                 logging.info(f"Formatted {processed_count}/{n_urls} URLs ({len(formatted_articles)} valid so far)")

    logging.info(f"Finished formatting. Found {len(formatted_articles)} valid articles.")
    process_and_save_articles(formatted_articles)
    logging.info("Scraping process finished.")