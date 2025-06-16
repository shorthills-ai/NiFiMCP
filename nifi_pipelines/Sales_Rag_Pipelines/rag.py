import os
import logging
from io import BytesIO
from typing import List, Dict, Any
from pptx import Presentation
from docx import Document
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import numpy as np
import httpx
from openai import AsyncAzureOpenAI
import weaviate
from weaviate.auth import AuthApiKey
from weaviate.classes.query import MetadataQuery
from fastapi import Request
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
import weaviate
from weaviate.auth import AuthApiKey
from weaviate.classes.query import MetadataQuery
import uvicorn
import traceback
import logging
import json
import os
import time
import numpy as np
from openai import AsyncAzureOpenAI
from httpx_aiohttp import AiohttpTransport
from aiohttp import ClientSession
import openai
from dotenv import load_dotenv
load_dotenv()
# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# === Load Env Variables ===
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
DRIVE_ID = os.getenv("DRIVE_ID")
WEAVIATE_URL = os.getenv("WEAVIATE_URL")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Accept": "application/json"}
import re
# === Logging Setup ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("combined_service")
CHAT_MODEL = "gpt-4o-mini"

# === FastAPI App ===
app = FastAPI(title="Combined RAG Service")

# ========== Service 1: Text Extraction ==========

def extract_text_from_docx(file_bytes: BytesIO) -> List[str]:
    doc = Document(file_bytes)
    chunks = []
    current_chunk = []
    current_size = 0
    max_chunk_size = 1028
    min_chunk_size = 200

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        if current_size + len(text) > max_chunk_size and current_chunk:
            chunk_text = " ".join(current_chunk)
            if len(chunk_text) >= min_chunk_size:
                chunks.append(chunk_text)
            current_chunk = []
            current_size = 0

        current_chunk.append(text)
        current_size += len(text)

    if current_chunk:
        chunk_text = " ".join(current_chunk)
        if len(chunk_text) >= min_chunk_size:
            chunks.append(chunk_text)

    return chunks

def extract_text_from_pptx(file_bytes: BytesIO) -> List[str]:
    prs = Presentation(file_bytes)
    chunks = []
    current_chunk = []
    current_size = 0
    max_chunk_size = 1028
    min_chunk_size = 100

    for slide_num, slide in enumerate(prs.slides, 1):
        slide_texts = [f"[Slide {slide_num}]"]
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                text = shape.text.strip()
                if text:
                    slide_texts.extend(line.strip() for line in text.split("\n") if line.strip())
        slide_content = " ".join(slide_texts)
        slide_size = len(slide_content)

        if current_size + slide_size > max_chunk_size and current_chunk:
            chunk_text = " ".join(current_chunk)
            if len(chunk_text) >= min_chunk_size:
                chunks.append(chunk_text)
            current_chunk = []
            current_size = 0

        current_chunk.append(slide_content)
        current_size += slide_size

        if current_size >= max_chunk_size:
            chunk_text = " ".join(current_chunk)
            if len(chunk_text) >= min_chunk_size:
                chunks.append(chunk_text)
            current_chunk = []
            current_size = 0

    if current_chunk:
        chunk_text = " ".join(current_chunk)
        if len(chunk_text) >= min_chunk_size:
            chunks.append(chunk_text)

    return chunks



@app.post("/extract-text")
async def extract_text(request: Request, file: UploadFile = File(...)):
    try:
        # === Log Headers ===
        headers = dict(request.headers)
        logger.info(f"Received request headers: {headers}")

        # Extract web_url from headers (case-insensitive match)
        web_url = headers.get("web_url") or headers.get("Web-Url") or None
        
        logger.info(f"Extracted web_url from headers: {web_url}")

        # === Read file ===
        file_bytes = BytesIO(await file.read())
        filename = file.filename
        logger.info(f"Received file: {filename}")

        filename_lower = filename.lower()

        if filename_lower.endswith(".docx"):
            chunks = extract_text_from_docx(file_bytes)
            file_type = "docx"
        elif filename_lower.endswith(".pptx"):
            chunks = extract_text_from_pptx(file_bytes)
            file_type = "pptx"
        else:
            logger.error("Unsupported file type")
            return JSONResponse(status_code=400, content={"error": "Unsupported file type"})

        # === Handle fallback for web_url ===
        if not web_url:
            logger.warning("No webUrl provided in headers; defaulting to filename")
            web_url = filename
        else:
            logger.info(f"Using provided webUrl: {web_url}")

        # === Process Chunks ===
        chunk_output = []
        for idx, chunk in enumerate(chunks):
            cleaned_chunk = " ".join(chunk.split())
            cleaned_chunk = "".join(char for char in cleaned_chunk if ord(char) < 128)

            chunk_metadata = {
                "content": cleaned_chunk,
                "metadata": {
                    "source_file": filename,
                    "file_type": file_type,
                    "chunk_index": idx,
                    "filepath": web_url
                }
            }
            logger.debug(f"Processed chunk {idx}: {chunk_metadata}")
            chunk_output.append(chunk_metadata)

        response_data = {"chunks": chunk_output}
        response_json = json.dumps(response_data, ensure_ascii=True, separators=(',', ':'))

        logger.info(f"Final JSON response preview: {response_json[:200]}")

        return JSONResponse(
            content=json.loads(response_json),
            media_type="application/json"
        )

    except Exception as e:
        logger.exception("Text extraction failed")
        return JSONResponse(status_code=500, content={"error": str(e)})

# ========== Service 2: Embedding ==========

class ChunkInput(BaseModel):
    content: str
    metadata: Dict[str, Any]

class EmbeddingRequest(BaseModel):
    chunks: List[ChunkInput]

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


def clean_json_string(json_str: str) -> str:
    """Clean and normalize JSON string."""
    # Remove any leading/trailing whitespace
    json_str = json_str.strip()
    
    # Find the first '{' and last '}'
    start = json_str.find('{')
    end = json_str.rfind('}')
    
    if start != -1 and end != -1:
        # Extract just the JSON object
        json_str = json_str[start:end + 1]
    
    # Remove whitespace between key and colon
    json_str = re.sub(r'"\s+:', '":', json_str)
    
    # Remove any BOM characters
    json_str = json_str.strip('\ufeff')
    
    return json_str

@app.post("/generate-embedding")
async def get_embeddings(request: Request):
    try:
        # Read the raw request
        body = await request.body()
        logger.info(f"Raw request size: {len(body)} bytes")
        
        try:
            # First try to parse the raw JSON
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                # If that fails, try to decode and clean the body
                body_str = body.decode('utf-8', errors='ignore')
                
                # Find all JSON objects in the string
                json_objects = []
                depth = 0
                start = -1
                
                for i, char in enumerate(body_str):
                    if char == '{':
                        if depth == 0:
                            start = i
                        depth += 1
                    elif char == '}':
                        depth -= 1
                        if depth == 0 and start != -1:
                            json_objects.append(body_str[start:i+1])
                            start = -1
                
                # If we found multiple JSON objects, take the first complete one
                if json_objects:
                    json_str = json_objects[0]
                    logger.info(f"Found {len(json_objects)} JSON objects, using first complete one")
                else:
                    raise ValueError("No complete JSON objects found in request body")
                
                # Clean the JSON string
                json_str = json_str.strip()
                # Remove any whitespace outside of quotes
                json_str = re.sub(r'\s+(?=(?:[^"]*"[^"]*")*[^"]*$)', '', json_str)
                
                try:
                    # Parse the cleaned JSON
                    data = json.loads(json_str)
                    # Validate it has the expected structure
                    if not isinstance(data, dict) or "chunks" not in data:
                        raise ValueError("Invalid JSON structure: missing 'chunks' key")
                except json.JSONDecodeError as je:
                    error_pos = je.pos
                    context = json_str[max(0, error_pos-50):min(len(json_str), error_pos+50)]
                    logger.error(f"JSON decode error at position {error_pos}: {context}")
                    raise
                
        except Exception as e:
            logger.error(f"JSON parsing error: {str(e)}")
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid JSON format",
                    "details": str(e)
                }
            )

        # Validate the chunks structure
        chunks = data.get("chunks", [])
        if not isinstance(chunks, list):
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid chunks format - expected a list"}
            )

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
                # Remove any non-ASCII characters
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
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to generate any embeddings"}
            )

        # Create final response with strict JSON encoding
        response_data = {"results": results}
        response_json = json.dumps(response_data, ensure_ascii=True, separators=(',', ':'))
        
        # Validate the response JSON
        try:
            json.loads(response_json)
        except json.JSONDecodeError as je:
            logger.error(f"Invalid response JSON: {je}")
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to generate valid response JSON"}
            )
        
        logger.info(f"Successfully generated embeddings for {len(results)} chunks")
        return JSONResponse(
            content=json.loads(response_json),
            media_type="application/json"
        )

    except Exception as e:
        logger.error(f"Embedding service failed: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Internal server error: {str(e)}"}
        )

class ChunkItem(BaseModel):
    content: str
    embedding: List[float]
    metadata: Dict[str, Any]

class UploadRequest(BaseModel):
    results: List[ChunkItem]


import base64

def encode_web_url(web_url: str) -> str:
    """Encodes a web_url to a format suitable for Microsoft Graph /shares/u! endpoint."""
    encoded = base64.urlsafe_b64encode(web_url.encode("utf-8")).decode("utf-8").rstrip("=")
    return f"u!{encoded}"

async def delete_from_onedrive(web_url: str) -> bool:
    try:
        encoded_url = encode_web_url(web_url)
        item_lookup_url = f"{GRAPH_BASE}/shares/{encoded_url}/driveItem"

        async with httpx.AsyncClient() as client:
            lookup_response = await client.get(item_lookup_url, headers=HEADERS)
            if lookup_response.status_code != 200:
                logger.warning(f"Could not resolve item for deletion: {web_url}")
                return False

            item = lookup_response.json()
            drive_id = item.get("parentReference", {}).get("driveId")
            item_id = item.get("id")

            if not drive_id or not item_id:
                logger.warning(f"Invalid drive_id/item_id from: {item}")
                return False

            delete_url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}"
            delete_response = await client.delete(delete_url, headers=HEADERS)

            if delete_response.status_code == 204:
                logger.info(f"Deleted file: {web_url}")
                return True
            else:
                logger.warning(f"Delete failed for {web_url}, status: {delete_response.status_code}")
                return False

    except Exception as e:
        logger.error(f"Delete error for {web_url}: {e}")
        return False

@app.post("/upload-data")
async def upload_to_weaviate(req: UploadRequest):
    try:
        client = weaviate.connect_to_weaviate_cloud(
            cluster_url=WEAVIATE_URL,
            auth_credentials=AuthApiKey(WEAVIATE_API_KEY),
            skip_init_checks=True
        )
        # collection = client.collections.get("Chunks")
        collection = client.collections.get("Test")
        logger.info("Connected to Weaviate and accessed 'Test' collection")

        inserted = []
        # files_to_delete = set()  # No longer needed

        for i, chunk in enumerate(req.results):
            try:
                collection.data.insert(
                    properties={
                        "content": chunk.content,
                        "metadata": chunk.metadata
                    },
                    vector=np.array(chunk.embedding).tolist()
                )
                inserted.append(f"Inserted chunk {i} from {chunk.metadata.get('source_file')}")
                # files_to_delete.add(chunk.metadata.get("filepath"))  # Skip collecting for deletion
            except Exception as insert_error:
                logger.warning(f"Failed to insert chunk {i}: {insert_error}")

        # === Skip file deletion from OneDrive ===
        # for file_url in files_to_delete:
        #     if file_url:
        #         await delete_from_onedrive(file_url)

        return {"status": "success", "inserted": inserted}

    except Exception as e:
        logger.error(f"Weaviate upload error: {e}")
        return {"status": "error", "message": str(e)}


####### Query Section ########
weaviate_client = weaviate.connect_to_weaviate_cloud(
    cluster_url=WEAVIATE_URL,
    auth_credentials=AuthApiKey(WEAVIATE_API_KEY),
    skip_init_checks=True
)
# # Maximum retries for API calls
MAX_RETRIES = 3
RETRY_DELAY = 2
async def generate_embedding1(text: str) -> np.ndarray:
    """Generate embedding using Azure OpenAI"""
    try:
        async with ClientSession() as session:
            async with AiohttpTransport(client=session) as aiohttp_transport:
                httpx_client = openai.DefaultAsyncHttpxClient(transport=aiohttp_transport)
                client = AsyncAzureOpenAI(
                    azure_endpoint=AZURE_OPENAI_ENDPOINT,
                    api_key=AZURE_OPENAI_API_KEY,
                    api_version=AZURE_OPENAI_API_VERSION,
                    http_client=httpx_client
                )
                response = await client.embeddings.create(
                    model=EMBEDDING_MODEL,
                    input=[text],
                    encoding_format="float"
                )
                await httpx_client.aclose()
                return np.array(response.data[0].embedding)
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        return None
async def generate_completion(prompt: str, system_prompt: str = None) -> str:
    """Generate completion using Azure OpenAI"""
    try:
        async with ClientSession() as session:
            async with AiohttpTransport(client=session) as aiohttp_transport:
                httpx_client = openai.DefaultAsyncHttpxClient(transport=aiohttp_transport)
                client = AsyncAzureOpenAI(
                    azure_endpoint=AZURE_OPENAI_ENDPOINT,
                    api_key=AZURE_OPENAI_API_KEY,
                    api_version=AZURE_OPENAI_API_VERSION,
                    http_client=httpx_client
                )
                try:
                    messages = []
                    if system_prompt:
                        messages.append({"role": "system", "content": system_prompt})
                    messages.append({"role": "user", "content": prompt})
 
                    logger.info(f"Generating completion with model: {CHAT_MODEL}")
                    response = await client.chat.completions.create(
                        model=CHAT_MODEL,
                        messages=messages,
                        temperature=0.3,
                        max_tokens=512
                    )
 
                    if not response or not response.choices:
                        logger.error("Empty response from OpenAI completion API")
                        return ""
 
                    return response.choices[0].message.content.strip()
                finally:
                    await httpx_client.aclose()
 
    except Exception as e:
        logger.error(f"Error generating completion: {str(e)}")
        return ""
 
 
@app.post("/query")
async def process_query(request: Request) -> Dict[str, Any]:
    try:
        logger.info("Received POST /query request")
 
        # Read and parse request body
        raw_body = await request.body()
        try:
            data = json.loads(raw_body.decode("utf-8").strip())
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON format: {e}")
 
        query = data.get("query")
        n_results = data.get("n_results", 3)
 
        if not query:
            raise HTTPException(status_code=400, detail="Missing 'query' in request body.")
 
        logger.info(f"Generating embedding for query: {query}")
 
        # Step 1: Generate embedding using Azure OpenAI
        query_embedding = await generate_embedding1(query)
        if query_embedding is None:
            raise HTTPException(status_code=500, detail="Failed to generate query embedding")
 
        # Step 2: Weaviate document retrieval
        logger.info("Sending query to Weaviate")
 
        try:
            # Get the collection
            collection = weaviate_client.collections.get("Chunks")
            
            # Perform vector search in Weaviate
            result = collection.query.near_vector(
                near_vector=query_embedding.tolist(),
                limit=n_results,
                return_metadata=MetadataQuery(distance=True)
            )
 
            if not hasattr(result, "objects") or not isinstance(result.objects, list):
                raise HTTPException(status_code=500, detail="Invalid response format from Weaviate")
 
            documents = []
            metadatas = []
            distances = []
 
            for obj in result.objects:
                if hasattr(obj, "properties"):
                    documents.append(obj.properties.get("content", ""))
                    metadatas.append(obj.properties.get("metadata", {}))
                    distances.append(obj.metadata.distance if hasattr(obj.metadata, "distance") else 0.0)
 
            if not documents:
                raise HTTPException(status_code=404, detail="No relevant documents found")
 
        except Exception as e:
            logger.error(f"Weaviate query failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to query Weaviate: {str(e)}")
 
        context = "\n\n".join([f"Document {i+1}: {doc}" for i, doc in enumerate(documents)])
 
        # Step 3: Generate answer using Azure OpenAI
        logger.info("Generating response using Azure OpenAI")
 
        system_prompt = """
You are a helpful assistant that answers questions using only the provided context.
Each answer must be well-structured, grammatically correct, and include relevant details such as source slide number and source file.
 
Your goal is to:
1. Extract meaningful, non-repetitive information from each context item.
2. Use commas, periods, and proper sentence structure.
3. Make sure the answer is insightful, with 2–3 key points per resource.
4. Avoid copying identical phrases across resources; ensure uniqueness.
5. If the context does not contain enough information, respond with: "I don't have enough information to answer this question based on the context."
 
Format the answer like this if the chunks are from ppt:
1. [Slide Number] Summary of the key insight with proper punctuation and grammar. Mention the unique takeaway.
2. [Slide Number] Different insight from another source. Ensure no repetition from the previous point.
3. [Slide Number] Another unique takeaway with source attribution.

Format the answer like this if the chunks are from docx:
1. Summary of the key insight with proper punctuation and grammar. Mention the unique takeaway.
2. Different insight from another source. Ensure no repetition from the previous point.
3. Another unique takeaway with source attribution.
 
If only 1 or 2 relevant contexts exist, only return those.
 
Only answer based on the provided context. Do not hallucinate or guess.
 
"""
 
        prompt = f"""Context:
{context}
 
Question: {query}
 
Please answer the question based only on the provided context."""
 
        try:
            llm_response = await generate_completion(prompt, system_prompt)
            if not llm_response:
                raise Exception("Empty response from Azure OpenAI")
            logger.info("LLM response generated successfully")
        except Exception as e:
            logger.error(f"Azure OpenAI generation failed: {str(e)}")
            traceback.print_exc()
            llm_response = f"I'm sorry, but I couldn't generate a response based on the provided context. Here are some relevant documents that might help answer your question about '{query}'."
            logger.info("Using fallback response")
 
        sources = []
        for i in range(len(documents)):
            sources.append({
                "text": documents[i],
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "relevance_score": 1.0 - distances[i] if i < len(distances) else 0
            })
 
        return {
            "answer": llm_response,
            "sources": sources
        }
 
    except Exception as e:
        logger.error(f"Exception occurred while processing query: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")
 
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)