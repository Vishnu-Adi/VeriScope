# FILE: push_to_db.py
# (Includes NameError fix and metadata size handling)
from pinecone import Pinecone, PodSpec
from gpt4all import Embed4All
from dotenv import load_dotenv
import os
import json
import uuid
from datetime import datetime
import logging
import sys

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

# --- Configuration ---
PINECONE_INDEX_NAME = "news-article"
ARTICLES_JSON_PATH = "articles.json"
LOCAL_VECTORS_PATH = "local_vectors.json"
BATCH_SIZE = 100
MAX_METADATA_STRING_FIELD_SIZE = 1024
MAX_METADATA_LIST_ITEMS = 50

# --- Initialize Clients ---
try:
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    if not pinecone_api_key:
        raise ValueError("PINECONE_API_KEY not found in environment variables.")
    pc = Pinecone(api_key=pinecone_api_key)
    embedder = Embed4All()
    logging.info("Pinecone and Embed4All clients initialized.")

    # New code to ensure the Pinecone index exists
    pinecone_environment = os.getenv("PINECONE_ENVIRONMENT", "gcp-starter")  # Get from .env or set default
    if PINECONE_INDEX_NAME not in pc.list_indexes():
        logging.info(f"Creating Pinecone index '{PINECONE_INDEX_NAME}'...")
        try:
            # Determine embedding dimension (CRITICAL!)
            embedder_temp = Embed4All()
            # Verify the path to hidden_size is correct for your Embed4All version
            embedding_dimension = embedder_temp.model.config.hidden_size
            del embedder_temp
            logging.info(f"Determined embedding dimension for {PINECONE_INDEX_NAME}: {embedding_dimension}")
        except Exception as embed_dim_err:
            logging.error(f"Could not determine embedding dimension automatically: {embed_dim_err}. Please set manually or fix Embed4All init.")
            embedding_dimension = 384  # Set a sensible default if auto-detection fails

        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=embedding_dimension,  # MUST match Embed4All output dimension
            metric="cosine",  # Good for semantic similarity with normalized embeddings
            spec=PodSpec(environment=pinecone_environment)  # Use your environment
        )
        logging.info(f"Index '{PINECONE_INDEX_NAME}' created.")
        # Optional: Add a small delay to allow index to initialize
        # import time
        # time.sleep(60)

except Exception as e:
    logging.error(f"Failed to initialize clients: {e}")
    sys.exit(1)

def upload_all():
    logging.info(f"Loading articles from {ARTICLES_JSON_PATH}...")
    try:
        with open(ARTICLES_JSON_PATH, "r", encoding='utf-8') as f:
            articles_data = json.load(f)
        logging.info(f"Loaded {len(articles_data)} articles.")

        if not isinstance(articles_data, list):
            logging.error(f"Expected a list of articles in {ARTICLES_JSON_PATH}, but got {type(articles_data)}")
            return

        if not articles_data:
            logging.warning(f"{ARTICLES_JSON_PATH} is empty. No vectors to process.")
            try:
                with open(LOCAL_VECTORS_PATH, "w", encoding='utf-8') as f:
                    json.dump({"vectors": []}, f)
                logging.info(f"Created empty {LOCAL_VECTORS_PATH}.")
            except IOError as e:
                 logging.error(f"Failed to write empty {LOCAL_VECTORS_PATH}: {e}")
            return

        pinecone_vectors = []
        local_vectors_data = []

        logging.info("Starting embedding and preparation...")

        try:
            with pc.Index(PINECONE_INDEX_NAME, pool_threads=10) as index:
                for i, article_row in enumerate(articles_data):
                    if not isinstance(article_row, dict):
                        logging.warning(f"Skipping item at index {i}, not a dictionary.")
                        continue

                    article_text = article_row.get("text")
                    article_title = article_row.get("title", "N/A")

                    if not article_text:
                        logging.warning(f"Skipping article '{article_title}' (index {i}) due to missing or empty text.")
                        continue

                    logging.debug(f"Embedding article {i+1}/{len(articles_data)}: '{article_title}' (Length: {len(article_text)})")

                    try:
                        values = embedder.embed(article_text)
                        article_id = str(uuid.uuid4())

                        metadata_for_pinecone = {}
                        fields_to_include_in_pinecone = ["url", "title", "authors", "publish_date", "brand", "keywords", "summary"]

                        for key in fields_to_include_in_pinecone:
                            value = article_row.get(key)
                            if value is None or value == '': continue

                            if key == "publish_date":
                                if isinstance(value, str):
                                     try:
                                         datetime.fromisoformat(value.replace('Z', '+00:00'))
                                         metadata_for_pinecone[key] = value
                                     except ValueError: pass
                            elif isinstance(value, (str, int, float, bool)):
                                if isinstance(value, str) and len(value.encode('utf-8')) > MAX_METADATA_STRING_FIELD_SIZE:
                                    logging.warning(f"Truncating long string field '{key}' for Pinecone metadata (article {article_id})")
                                    truncated_value = value.encode('utf-8')[:MAX_METADATA_STRING_FIELD_SIZE].decode('utf-8', errors='ignore')
                                    metadata_for_pinecone[key] = truncated_value + "..."
                                else:
                                    metadata_for_pinecone[key] = value
                            elif isinstance(value, list) and all(isinstance(item, str) for item in value):
                                if len(value) > MAX_METADATA_LIST_ITEMS:
                                    logging.warning(f"Truncating list field '{key}' (length {len(value)}) for Pinecone metadata (article {article_id})")
                                    metadata_for_pinecone[key] = value[:MAX_METADATA_LIST_ITEMS]
                                else:
                                     metadata_for_pinecone[key] = value

                        pinecone_vec = {"id": article_id, "values": values, "metadata": metadata_for_pinecone}
                        pinecone_vectors.append(pinecone_vec)

                        local_metadata = article_row.copy()
                        local_metadata['original_id_in_pinecone'] = article_id
                        local_vec_entry = {"id": article_id, "values": values, "metadata": local_metadata}
                        local_vectors_data.append(local_vec_entry)

                    except Exception as embed_err:
                        logging.error(f"Error processing article '{article_title}' (index {i}): {embed_err}", exc_info=True)
                        continue

                    if len(pinecone_vectors) >= BATCH_SIZE or (i == len(articles_data) - 1 and pinecone_vectors):
                        logging.info(f"Upserting batch of {len(pinecone_vectors)} vectors to Pinecone (up to index {i})...")
                        try:
                            index.upsert(vectors=pinecone_vectors)
                            logging.info(f"Successfully upserted batch ending at index {i}.")
                            pinecone_vectors = []
                        except Exception as upsert_err:
                            logging.error(f"Failed to upsert batch to Pinecone: {upsert_err}")
                            failed_ids = [v.get('id', 'N/A') for v in pinecone_vectors]
                            logging.error(f"Failed batch IDs: {failed_ids}")
                            pinecone_vectors = []

                logging.info("Finished processing all articles.")

        except Exception as pinecone_err:
            logging.error(f"Error interacting with Pinecone index '{PINECONE_INDEX_NAME}': {pinecone_err}", exc_info=True)

        if local_vectors_data:
            logging.info(f"Saving {len(local_vectors_data)} processed vectors to {LOCAL_VECTORS_PATH}")
            try:
                output_structure = {"vectors": local_vectors_data}
                with open(LOCAL_VECTORS_PATH, "w", encoding='utf-8') as f:
                    json.dump(output_structure, f, ensure_ascii=False, indent=2)
            except IOError as e:
                logging.error(f"Failed to write {LOCAL_VECTORS_PATH}: {e}")
            except Exception as e:
                logging.error(f"An unexpected error occurred while writing {LOCAL_VECTORS_PATH}: {e}")
        else:
             logging.warning(f"No valid local vectors generated, {LOCAL_VECTORS_PATH} will not be created/updated.")

    except FileNotFoundError:
        logging.error(f"File not found: {ARTICLES_JSON_PATH}")
        return
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from {ARTICLES_JSON_PATH}: {e}")
        return
    except Exception as load_err:
        logging.error(f"Failed to load or prepare articles data: {load_err}", exc_info=True)
        return

if __name__ == "__main__":
    upload_all()
    logging.info("push_to_db.py finished.")