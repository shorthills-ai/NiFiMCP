#!/usr/bin/env python3
import os
import sys
import json
import logging
import base64
from typing import List, Dict, Any
from dotenv import load_dotenv
import numpy as np
import weaviate
from weaviate.auth import AuthApiKey

# Load environment variables
load_dotenv()

# === Configuration ===
WEAVIATE_URL = os.getenv("WEAVIATE_URL")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")

# === Logging ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def encode_web_url(web_url: str) -> str:
    """Encodes a web_url to a format suitable for Microsoft Graph /shares/u! endpoint."""
    encoded = base64.urlsafe_b64encode(web_url.encode("utf-8")).decode("utf-8").rstrip("=")
    return f"u!{encoded}"

def main():
    try:
        # Read input from stdin
        input_data = sys.stdin.read()
        
        # Parse input JSON
        try:
            data = json.loads(input_data)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}")
            error_result = {"error": f"Invalid JSON format: {e}"}
            print(json.dumps(error_result))
            sys.exit(1)

        # Validate results structure
        results = data.get("results", [])
        if not isinstance(results, list):
            error_result = {"error": "Invalid results format - expected a list"}
            print(json.dumps(error_result))
            sys.exit(1)

        # Connect to Weaviate
        client = weaviate.connect_to_weaviate_cloud(
            cluster_url=WEAVIATE_URL,
            auth_credentials=AuthApiKey(WEAVIATE_API_KEY),
            skip_init_checks=True
        )
        collection = client.collections.get("Sales")
        logger.info("Connected to Weaviate and accessed 'Sales' collection")

        inserted = []
        
        for i, chunk in enumerate(results):
            try:
                if not isinstance(chunk, dict):
                    logger.warning(f"Skipping result {i}: Not a dictionary")
                    continue
                    
                content = chunk.get("content")
                embedding = chunk.get("embedding")
                metadata = chunk.get("metadata", {})
                
                if not content or not embedding:
                    logger.warning(f"Skipping result {i}: Missing content or embedding")
                    continue

                # Insert into Weaviate
                collection.data.insert(
                    properties={
                        "content": content,
                        "metadata": metadata
                    },
                    vector=embedding
                )
                
                inserted.append(f"Inserted chunk {i} from {metadata.get('source_file', 'unknown')}")
                logger.info(f"Successfully inserted chunk {i}")
                
            except Exception as insert_error:
                logger.error(f"Failed to insert chunk {i}: {insert_error}")
                continue

        # Close connection
        client.close()

        # Output results
        response_data = {"status": "success", "inserted": inserted}
        print(json.dumps(response_data, ensure_ascii=True))
        
        logger.info(f"Successfully inserted {len(inserted)} chunks")

    except Exception as e:
        logger.error(f"Weaviate upload error: {e}")
        error_result = {"status": "error", "message": str(e)}
        print(json.dumps(error_result))
        sys.exit(1)

if __name__ == "__main__":
    main()