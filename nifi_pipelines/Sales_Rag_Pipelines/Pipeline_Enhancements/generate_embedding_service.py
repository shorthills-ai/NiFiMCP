

#!/usr/bin/env python3
import os
import sys
import json
import logging
import asyncio
import re
from typing import List, Dict, Any
from dotenv import load_dotenv
import numpy as np
import httpx
from openai import AsyncAzureOpenAI

# Load environment variables
load_dotenv()

# === Configuration ===
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")

# === Logging ===
# Configure logging to write to stderr only (not stdout) to avoid contaminating JSON output
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr  # Force logs to stderr
)
logger = logging.getLogger(__name__)

def extract_json_from_input(input_data: str) -> dict:
    """Extract JSON from input that might contain extra data"""
    try:
        # Method 1: Try to parse the entire input as JSON
        return json.loads(input_data)
    except json.JSONDecodeError as e:
        logger.warning(f"Full JSON parsing failed: {e}")
        
        # Method 2: Try to find JSON object boundaries
        try:
            # Look for the first opening brace and try to find the matching closing brace
            start_idx = input_data.find('{')
            if start_idx == -1:
                raise ValueError("No JSON object found in input")
            
            # Find the matching closing brace
            brace_count = 0
            end_idx = start_idx
            for i, char in enumerate(input_data[start_idx:], start_idx):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i
                        break
            
            if brace_count != 0:
                raise ValueError("Unmatched braces in JSON")
            
            json_str = input_data[start_idx:end_idx + 1]
            logger.info(f"Extracted JSON substring from position {start_idx} to {end_idx}")
            return json.loads(json_str)
            
        except Exception as e2:
            logger.warning(f"JSON extraction failed: {e2}")
            
            # Method 3: Try to find JSON using regex
            try:
                # Look for JSON pattern starting with {"chunks"
                json_pattern = r'(\{"chunks".*?\}\s*\})'
                match = re.search(json_pattern, input_data, re.DOTALL)
                if match:
                    json_str = match.group(1)
                    logger.info("Found JSON using regex pattern")
                    return json.loads(json_str)
                else:
                    raise ValueError("No JSON pattern found")
            except Exception as e3:
                logger.error(f"All JSON parsing methods failed: {e3}")
                raise ValueError(f"Could not parse JSON from input: {e}")

async def generate_embedding(text: str):
    try:
        async with httpx.AsyncClient() as client:
            openai_client = AsyncAzureOpenAI(
                azure_endpoint=AZURE_OPENAI_ENDPOINT,
                api_key=AZURE_OPENAI_API_KEY,
                api_version=AZURE_OPENAI_API_VERSION,
                http_client=client
            )
            logger.info(f"Generating embedding for: {text[:80]}...")
            response = await openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=[text],
                encoding_format="float"
            )
            return np.array(response.data[0].embedding)
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        return None

async def main():
    try:
        # Read input from stdin
        input_data = sys.stdin.read()
        
        if not input_data.strip():
            logger.error("No input data received")
            error_result = {"error": "No input data received"}
            print(json.dumps(error_result), flush=True)
            sys.exit(1)
        
        logger.info(f"Received input data of length: {len(input_data)}")
        
        # Parse input JSON with robust extraction
        try:
            data = extract_json_from_input(input_data)
        except Exception as e:
            logger.error(f"JSON parsing error: {e}")
            logger.error(f"Input data preview: {repr(input_data[:500])}")
            error_result = {"error": f"Invalid JSON format: {e}"}
            print(json.dumps(error_result), flush=True)
            sys.exit(1)

        # Validate chunks structure
        chunks = data.get("chunks", [])
        if not isinstance(chunks, list):
            error_result = {"error": "Invalid chunks format - expected a list"}
            print(json.dumps(error_result), flush=True)
            sys.exit(1)

        logger.info(f"Processing {len(chunks)} chunks")
        results = []
        
        for i, chunk in enumerate(chunks):
            try:
                if not isinstance(chunk, dict):
                    logger.warning(f"Skipping chunk {i}: Not a dictionary")
                    continue
                    
                content = chunk.get("content")
                metadata = chunk.get("metadata", {})
                
                if not content:
                    logger.warning(f"Skipping chunk {i}: Missing content")
                    continue

                # Clean and normalize the content
                content = str(content).strip()
                content = "".join(char for char in content if ord(char) < 128)
                
                if not content:
                    logger.warning(f"Skipping chunk {i}: Empty content after cleaning")
                    continue

                logger.info(f"Processing chunk {i} with content length: {len(content)}")
                embedding = await generate_embedding(content)
                
                if embedding is not None:
                    results.append({
                        "content": content,
                        "embedding": embedding.tolist(),
                        "metadata": metadata
                    })
                    logger.info(f"Successfully processed chunk {i}")
                else:
                    logger.warning(f"Failed to generate embedding for chunk {i}")
                    
            except Exception as chunk_error:
                logger.error(f"Error processing chunk {i}: {chunk_error}")
                continue

        if not results:
            error_result = {"error": "Failed to generate any embeddings"}
            print(json.dumps(error_result), flush=True)
            sys.exit(1)

        # Output results - ensure clean output
        response_data = {"results": results}
        json_output = json.dumps(response_data, ensure_ascii=True)
        
        # Clear stdout buffer and output only JSON
        sys.stdout.flush()
        print(json_output, flush=True)
        
        # Log success to stderr
        logger.info(f"Successfully generated embeddings for {len(results)} chunks")

    except Exception as e:
        logger.error(f"Embedding service failed: {e}")
        error_result = {"error": f"Internal server error: {e}"}
        print(json.dumps(error_result), flush=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())