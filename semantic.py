# FILE: semantic.py
# (Includes fix for TypeError on execute call)
from pinecone import Pinecone, PodSpec
import instructor # Not used here
from openai import OpenAI # Not used here
import os
from dotenv import load_dotenv
from supabase import create_client
from gpt4all import Embed4All
import uuid
import logging
import time
import sys

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

# --- Configuration ---
PINECONE_SEMANTIC_INDEX_NAME = "semantic-search"
BATCH_SIZE = 100

# --- Initialize Clients ---
try:
    pinecone_semantic_api_key = os.getenv("PINECONE_SEMANTIC_API_KEY", os.getenv("PINECONE_API_KEY"))
    pinecone_semantic_environment = os.getenv("PINECONE_SEMANTIC_ENVIRONMENT", os.getenv("PINECONE_ENVIRONMENT", "gcp-starter"))
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not all([pinecone_semantic_api_key, supabase_url, supabase_key]):
        raise ValueError("Missing one or more required environment variables (Pinecone Semantic/API, Supabase).")

    pc = Pinecone(api_key=pinecone_semantic_api_key)

    if PINECONE_SEMANTIC_INDEX_NAME not in pc.list_indexes():
       logging.info(f"Creating semantic index '{PINECONE_SEMANTIC_INDEX_NAME}'...")
       try:
           embedder_temp = Embed4All()
           embedding_dimension = embedder_temp.model.config.hidden_size
           del embedder_temp
           logging.info(f"Determined embedding dimension: {embedding_dimension}")
       except Exception as embed_dim_err:
           logging.error(f"Could not determine embedding dimension automatically: {embed_dim_err}. Please set manually or fix Embed4All init.")
           embedding_dimension = 384 # Fallback
       pc.create_index(name=PINECONE_SEMANTIC_INDEX_NAME, dimension=embedding_dimension, metric="cosine", spec=PodSpec(environment=pinecone_semantic_environment))

    index = pc.Index(PINECONE_SEMANTIC_INDEX_NAME)
    supabase = create_client(supabase_url, supabase_key)
    embedder = Embed4All()
    logging.info("Pinecone (semantic), Supabase, and Embed4All clients initialized.")

except Exception as e:
    logging.error(f"Failed to initialize clients for semantic.py: {e}")
    sys.exit(1)

# --- Main Logic (runs on script execution) ---
logging.info("Fetching clusters with non-NULL synthesis from Supabase...")
syntheses_data = []
try:
    query = supabase.table("clusters").select("id, synthesis").not_("synthesis", "is", None)
    response = query.execute()

    if hasattr(response, 'error') and response.error:
         raise Exception(f"Supabase error: {response.error.message}")

    if response and hasattr(response, 'data'):
        syntheses_data = response.data
        logging.info(f"Found {len(syntheses_data)} clusters with synthesis.")
    else:
        logging.warning("Supabase response did not contain expected 'data' attribute or returned no data.")

except Exception as e:
    logging.error(f"Failed to fetch syntheses from Supabase: {e}", exc_info=True)
    # syntheses_data remains []

vectors_to_upsert = []

if syntheses_data:
    logging.info("Processing syntheses and generating embeddings...")
    total_excerpts = 0
    for i, synth_dict in enumerate(syntheses_data):
        cluster_id = synth_dict.get("id")
        synthesis_text = synth_dict.get("synthesis")

        if not cluster_id or not synthesis_text:
            logging.warning(f"Skipping cluster at index {i} due to missing ID or synthesis.")
            continue

        try:
            sentences = [s.strip() for s in synthesis_text.split('.') if s.strip()]
            excerpts = []
            for j in range(0, len(sentences), 2):
                excerpt = sentences[j] + "."
                if j + 1 < len(sentences):
                    excerpt += " " + sentences[j+1] + "."
                if len(excerpt) > 20: excerpts.append(excerpt)
            if not excerpts and len(sentences) == 1 and len(sentences[0]) > 20:
                excerpts.append(sentences[0] + ".")

            logging.debug(f"Cluster {cluster_id}: Generated {len(excerpts)} excerpts.")
            total_excerpts += len(excerpts)

            for excerpt_text in excerpts:
                try:
                    embedding_values = embedder.embed(excerpt_text)
                    vectors_to_upsert.append({
                        "id": str(uuid.uuid4()),
                        "values": embedding_values,
                        "metadata": {"cluster_id": cluster_id, "excerpt": excerpt_text},
                    })
                except Exception as embed_err:
                    logging.error(f"Failed to embed excerpt for cluster {cluster_id}: {embed_err}")
                    continue

        except Exception as split_err:
            logging.error(f"Error processing synthesis for cluster {cluster_id}: {split_err}")
            continue

        if len(vectors_to_upsert) >= BATCH_SIZE or (i == len(syntheses_data) - 1 and vectors_to_upsert):
            logging.info(f"Upserting batch of {len(vectors_to_upsert)} excerpt vectors to Pinecone (semantic-search)...")
            try:
                index.upsert(vectors=vectors_to_upsert)
                logging.info(f"Successfully upserted semantic batch ending at index {i}.")
                vectors_to_upsert = []
                # time.sleep(0.1) # Optional delay
            except Exception as upsert_err:
                logging.error(f"Failed to upsert batch to Pinecone semantic index: {upsert_err}")
                failed_ids = [v.get('id', 'N/A') for v in vectors_to_upsert]
                logging.error(f"Failed semantic batch IDs: {failed_ids}")
                vectors_to_upsert = []

    logging.info(f"Finished processing syntheses. Generated {total_excerpts} total excerpts.")
else:
    logging.info("No syntheses found to process for semantic search index.")

logging.info("semantic.py finished.")