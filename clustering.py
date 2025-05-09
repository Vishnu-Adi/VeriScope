# FILE: clustering.py
# (Includes fixes for TypeError, URL column, AI call handling)
from pinecone import Pinecone
from dotenv import load_dotenv
import os
import json
from collections import defaultdict
from supabase import create_client, Client
import uuid
from datetime import datetime, timezone
import models # Ensure models.py is present and correct
import instructor
from openai import OpenAI
import logging
import sys

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

# --- Configuration ---
ONE_TIME_RUN = True
PINECONE_INDEX_NAME = "news-article"
# !!! IMPORTANT: Verify this matches your actual Supabase column name !!!
SUPABASE_ARTICLES_URL_COLUMN = "url"
SIMILARITY_THRESHOLD = 0.5
MIN_ARTICLES_FOR_SYNTHESIS = 3
ARTICLES_FOR_SYNTHESIS_SAMPLE = 4
VECTORS_FILE_PATH = "local_vectors.json"
PROCESS_LIMIT = None # Limit articles processed from JSON for testing (e.g., 1000)

# --- Initialize Clients ---
try:
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not all([pinecone_api_key, openai_api_key, supabase_url, supabase_key]):
        raise ValueError("Missing one or more required environment variables.")

    pc = Pinecone(api_key=pinecone_api_key)
    client = instructor.patch(OpenAI(api_key=openai_api_key))
    supabase = create_client(supabase_url, supabase_key)
    logging.info("Pinecone, OpenAI, and Supabase clients initialized.")
except Exception as e:
    logging.error(f"Failed to initialize clients: {e}")
    sys.exit(1)

# --- UnionFind Class ---
class UnionFind:
    def __init__(self, articles_data):
        if not isinstance(articles_data, list) or not all(isinstance(a, dict) and 'id' in a for a in articles_data):
             raise ValueError("UnionFind input must be a list of dictionaries with 'id' keys.")
        self.root = {article["id"]: article["id"] for article in articles_data}
    def find(self, x):
        if x not in self.root: return None
        if x == self.root[x]: return x
        self.root[x] = self.find(self.root[x])
        return self.root[x]
    def union(self, x, y):
        rootX = self.find(x)
        rootY = self.find(y)
        if rootX is None or rootY is None: return
        if rootX != rootY: self.root[rootY] = rootX

# --- Helper Functions ---
def get_cluster_articles(cluster_id):
    global supabase
    try:
        response = supabase.table("articles").select("*").eq("cluster_id", cluster_id).execute()
        if response.data: logging.info(f"Articles for cluster {cluster_id}: {[a.get('title', 'N/A') for a in response.data]}")
        else: logging.warning(f"No articles found for cluster {cluster_id}")
        if response.error: logging.error(f"Supabase error fetching articles for cluster {cluster_id}: {response.error.message}")
    except Exception as e: logging.error(f"Error fetching articles for cluster {cluster_id}: {e}")

def gen_ai_synthesis(articles, emphasis_on=None):
    global client
    if not articles: return {"synthesis": None, "title": None, "key_takeaways": None, "people": None, "events": None, "statistics": None}
    article_texts = [a.get('text', '') for a in articles if a.get('text')]
    article_titles = [a.get('title', 'Untitled') for a in articles]
    # Add debug logs for input values
    logging.debug(f"Input article texts for synthesis: {article_texts}")
    logging.debug(f"Input article titles for synthesis: {article_titles}")
    if not article_texts: # If all articles lacked text
        logging.warning("gen_ai_synthesis called but no valid text found in articles.")
        return {"synthesis": None, "title": None, "key_takeaways": None, "people": None, "events": None, "statistics": None}

    emphasis_text = emphasis_on.get('text', '') if emphasis_on else ''
    logging.info(f"Generating synthesis for {len(articles)} articles. Titles: {article_titles}")
    try:
        logging.info("Calling OpenAI completion 1 for cluster synthesis...")  # New logging before API call
        response1 = client.chat.completions.create(
            model="gpt-3.5-turbo",
            response_model=models.UnbiasedResponse,
            messages=[
                {"role": "system", "content": f"Given a list of articles, write a long, cumulative, detailed, unbiased news report. {'In your report, place an emphasis on the article below.' if emphasis_on else ''} Provide a title as well. Aim for at least 500 words."},
                {"role": "user", "content": f"{article_texts}"},
                {"role": "user", "content": f"List of article titles: {article_titles}"},
            ] + ([{"role": "user", "content": f"This article is the most recent and important: {emphasis_text}."}] if emphasis_on else []),
        )
        synthesis_text = response1.text if response1 and response1.text else None
        if not synthesis_text: raise ValueError("Synthesis text generation failed.")

        response2 = client.chat.completions.create(
            model="gpt-3.5-turbo",
            response_model=models.ArticleData,
            messages=[
                {"role": "system", "content": "Extract key takeaways, people, events, and statistics from the provided news report text."},
                {"role": "user", "content": synthesis_text},
            ],
        )
        response1_data = response1.model_dump() if response1 else {}
        response2_data = response2.model_dump() if response2 else {}
        logging.info(f"Successfully generated synthesis. Title: {response1_data.get('title', 'N/A')}")
        return {"synthesis": response1_data.get("text"), "title": response1_data.get("title"), "key_takeaways": response2_data.get("key_takeaways"), "people": response2_data.get("people"), "events": response2_data.get("events"), "statistics": response2_data.get("statistics")}
    except Exception as e:
        logging.error(f"Error during AI synthesis generation: {e}", exc_info=True)
        logging.error(f"Articles attempted: {json.dumps([{'id': a.get('id', 'N/A'), 'title': a.get('title', 'N/A')} for a in articles], default=str)}")
        return {"synthesis": None, "title": None, "key_takeaways": None, "people": None, "events": None, "statistics": None}

# --- Main Clustering Logic ---
def get_clusters():
    global supabase, pc, client
    if not ONE_TIME_RUN:
        logging.error("Dynamic clustering mode (ONE_TIME_RUN=False) is not supported in this script version.")
        return

    logging.info("Starting ONE_TIME_RUN clustering process.")
    try:
        with open(VECTORS_FILE_PATH, "r", encoding='utf-8') as f:
            all_articles_data = json.load(f)["vectors"]
            articles_data = all_articles_data[:PROCESS_LIMIT] if PROCESS_LIMIT else all_articles_data
            logging.info(f"Loaded {len(articles_data)} articles with embeddings from '{VECTORS_FILE_PATH}'.")
    except Exception as e:
        logging.error(f"Error reading or parsing vectors file '{VECTORS_FILE_PATH}': {e}")
        return

    if not articles_data or not isinstance(articles_data[0].get('metadata'), dict):
         logging.error(f"Invalid structure in {VECTORS_FILE_PATH}.")
         return

    try:
        index = pc.Index(PINECONE_INDEX_NAME)
        logging.info(f"Connected to Pinecone index '{PINECONE_INDEX_NAME}'.")
    except Exception as e:
        logging.error(f"Failed to connect to Pinecone index '{PINECONE_INDEX_NAME}': {e}")
        return

    uf = UnionFind(articles_data)
    mappings = {article["id"]: article.get("metadata", {}) for article in articles_data}
    valid_article_ids = set(article["id"] for article in articles_data)

    logging.info("Querying Pinecone for similarities...")
    for i, article in enumerate(articles_data):
        if (i + 1) % 100 == 0: logging.info(f"Pinecone query progress: {i + 1}/{len(articles_data)}")
        if "values" not in article or not article["values"]: continue
        if "id" not in article: continue
        try:
            query_response = index.query(vector=article["values"], top_k=20, include_metadata=False)
            filtered_matches = [
                match["id"] for match in query_response["matches"]
                if match["score"] > SIMILARITY_THRESHOLD and match["id"] != article["id"] and match["id"] in valid_article_ids
            ]
            for m_id in filtered_matches: uf.union(article["id"], m_id)
        except Exception as e: logging.error(f"Error querying Pinecone for article {article['id']}: {e}")

    grouped_articles = defaultdict(list)
    for ad in articles_data:
        if 'id' not in ad: continue
        root = uf.find(ad["id"])
        if root is not None: grouped_articles[root].append(ad["id"])

    logging.info(f"Formed {len(grouped_articles)} potential clusters.")

    for cluster_root_id, article_ids_in_cluster in grouped_articles.items():
        cluster_uuid = str(uuid.uuid4())
        logging.info(f"Processing cluster {cluster_uuid} (root {cluster_root_id}) with {len(article_ids_in_cluster)} articles.")
        logging.info(f"Cluster {cluster_uuid} (Root: {cluster_root_id}) - Size: {len(article_ids_in_cluster)}")  # New logging

        cluster_articles_metadata = [mappings[aid] for aid in article_ids_in_cluster if aid in mappings]

        synthesis_result = {}
        # TEMPORARY DEBUGGING - Force synthesis for debugging even for a small cluster:
        if len(article_ids_in_cluster) >= 1:  # Changed from MIN_ARTICLES_FOR_SYNTHESIS
            logging.info(f"DEBUG: Forcing synthesis for cluster {cluster_uuid} with {len(article_ids_in_cluster)} articles...")
        else:
            logging.info(f"Cluster {cluster_uuid} has only {len(article_ids_in_cluster)} articles, skipping synthesis.")  # This block is now unlikely to run due to forced synthesis

        try:
            articles_to_synthesize = sorted(
                cluster_articles_metadata,
                key=lambda x: datetime.fromisoformat(x.get("publish_date", "1970-01-01T00:00:00Z").replace('Z', '+00:00')) if x.get("publish_date") else datetime.min,
                reverse=True
            )[:ARTICLES_FOR_SYNTHESIS_SAMPLE]
            synthesis_result = gen_ai_synthesis(articles_to_synthesize)
            if synthesis_result and synthesis_result.get("synthesis"):
                 cluster_db_data.update(synthesis_result)
            else:
                 logging.warning(f"AI Synthesis failed for cluster {cluster_uuid}, will insert NULL values.")
        except Exception as e:
             logging.error(f"Failed to prepare articles or generate synthesis for cluster {cluster_uuid}: {e}")

        try:
            for key in ["people", "events", "statistics", "key_takeaways"]:
                if cluster_db_data[key] is not None:
                     try: json.dumps(cluster_db_data[key])
                     except TypeError:
                          logging.warning(f"Converting non-serializable data in '{key}' for cluster {cluster_uuid} to string.")
                          cluster_db_data[key] = str(cluster_db_data[key])

            response = supabase.table("clusters").upsert(cluster_db_data).execute()
            if hasattr(response, 'error') and response.error:
                 logging.error(f"Supabase upsert error for cluster {cluster_uuid}: {response.error.message}")
                 continue
            else:
                 logging.info(f"Upserted cluster {cluster_uuid} to Supabase.")
        except Exception as e:
            logging.error(f"Failed to upsert cluster {cluster_uuid}: {e}", exc_info=True)
            continue

        for article_id in article_ids_in_cluster:
            if article_id not in mappings: continue
            article_metadata = mappings[article_id]
            article_pk = article_id

            try:
                response_tuple = supabase.table("articles").select('id', count='exact').eq('id', article_pk).execute()
                actual_count = response_tuple[1] if isinstance(response_tuple, tuple) and len(response_tuple) > 1 else None

                if actual_count is not None and actual_count > 0:
                    logging.info(f"Article {article_pk} exists. Updating cluster_id to {cluster_uuid}.")
                    update_response = supabase.table("articles").update({"cluster_id": cluster_uuid}).eq("id", article_pk).execute()
                    if hasattr(update_response, 'error') and update_response.error:
                         logging.error(f"Failed to update cluster_id for article {article_pk}: {update_response.error.message}")
                    continue

                authors = article_metadata.get("authors", [])
                if not isinstance(authors, list): authors = [str(authors)]
                publish_date_iso = None
                publish_date_str = article_metadata.get("publish_date")
                if isinstance(publish_date_str, str):
                    try: publish_date_iso = datetime.fromisoformat(publish_date_str.replace('Z', '+00:00')).isoformat()
                    except ValueError: pass
                elif isinstance(publish_date_str, datetime): publish_date_iso = publish_date_str.isoformat()
                if publish_date_iso is None: publish_date_iso = datetime.now(timezone.utc).isoformat()

                images_list = article_metadata.get("images") or []
                movies_list = article_metadata.get("movies") or []
                keywords_list = article_metadata.get("keywords") or []

                article_insert_data = {
                    "id": article_pk, "cluster_id": cluster_uuid,
                    "text": article_metadata.get("text", ""),
                    "title": article_metadata.get("title", "Untitled"),
                    "authors": authors, "publish_date": publish_date_iso,
                    "top_image": article_metadata.get("top_image"),
                    "images": images_list[:5], "movies": movies_list[:5],
                    "keywords": keywords_list,
                    "summary": article_metadata.get("summary"), # Uses newspaper3k summary
                    "publisher": article_metadata.get("brand"),
                    SUPABASE_ARTICLES_URL_COLUMN: article_metadata.get("url") # Use configured column name
                }

                insert_response = supabase.table("articles").insert(article_insert_data).execute()
                if hasattr(insert_response, 'error') and insert_response.error:
                     logging.error(f"Supabase insert error for article {article_pk}: {insert_response.error.message}")
                     logging.error(f"Failing article data: {json.dumps(article_insert_data, default=str)}")
                else:
                     logging.info(f"Inserted article {article_pk} for cluster {cluster_uuid}.")

            except Exception as e:
                logging.error(f"Failed processing article {article_pk} for cluster {cluster_uuid}: {e}", exc_info=True)
                logging.error(f"Article metadata causing error: {json.dumps(article_metadata, default=str)}")

# --- Main Execution ---
if __name__ == "__main__":
    logging.info("Clustering script started.")
    try:
        get_clusters()
        logging.info("Clustering process finished.")
    except Exception as e:
        logging.error(f"An unhandled error occurred during the clustering process: {e}", exc_info=True)
    logging.info("Clustering script finished.")