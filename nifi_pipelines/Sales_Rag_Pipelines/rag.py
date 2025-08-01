import os
import logging
from io import BytesIO
from typing import List, Dict, Any, Optional
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
from fastapi import Header, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from openai import AsyncAzureOpenAI
from httpx_aiohttp import AiohttpTransport
from aiohttp import ClientSession
import openai
import grpc
from dotenv import load_dotenv
# JWT imports
import jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
# Token tracking imports
import csv
import tiktoken
from pathlib import Path


load_dotenv()


# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# === Load Env Variables ===
#ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
DRIVE_ID = os.getenv("DRIVE_ID")
WEAVIATE_URL = os.getenv("WEAVIATE_URL")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")


# JWT Security Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))  # 24 hours default


# Validate required JWT configuration
if not JWT_SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY environment variable is required")
if JWT_SECRET_KEY == "your-super-secret-jwt-key-change-this-in-production":
    raise ValueError("Please set a secure JWT_SECRET_KEY in your .env file")


# Admin credentials for /token endpoint authentication
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")


# Validate admin credentials
if not ADMIN_PASSWORD:
    raise ValueError("ADMIN_PASSWORD environment variable is required for /token endpoint")


GRAPH_BASE = "https://graph.microsoft.com/v1.0"
#HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Accept": "application/json"}


import re
from difflib import SequenceMatcher


# === Logging Setup ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("combined_service")


CHAT_MODEL = "gpt-4o-mini"

# === Token Cost Configuration (in USD per million tokens) ===
EMBEDDING_COST_PER_MILLION = 0.10  # $0.10 per million tokens
INPUT_COST_PER_MILLION = 0.15      # $0.15 per million tokens  
OUTPUT_COST_PER_MILLION = 0.60     # $0.60 per million tokens

# USD to INR conversion rate (update as needed)
USD_TO_INR = 87.59  # Approximate rate

# CSV file path for logging
CSV_LOG_FILE = "query_metrics.csv"


# === JWT Security Setup ===
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Pydantic models for authentication
class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class UserPayload(BaseModel):
    exp: datetime  # Only expiration time needed
    valid: bool = True


def verify_password(plain_password, hashed_password):
    """Verify a password against its hash - DEPRECATED"""
    # This function is no longer needed
    pass


def get_password_hash(password):
    """Hash a password - DEPRECATED"""
    # This function is no longer needed
    pass


def create_access_token():
    """Create a JWT access token using only JWT secret key and expiration hours"""
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    
    to_encode = {
        "exp": expire
    }
    
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token and extract token information"""
    token = credentials.credentials
    
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        
        # Check if token is expired
        exp = payload.get("exp")
        if exp is None or datetime.utcnow() > datetime.fromtimestamp(exp):
            raise HTTPException(
                status_code=401,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        return {"exp": exp, "valid": True}
        
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


# authenticate_user function removed - no longer needed


def authenticate_user(username: str, password: str):
    """Authenticate user with admin credentials for /token endpoint"""
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        return {"username": username, "authenticated": True}
    return None


# === Token Tracking Functions ===

def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Count tokens in text using tiktoken"""
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except Exception as e:
        logger.warning(f"Token counting failed: {e}, using approximation")
        # Fallback: approximate 4 characters per token
        return len(text) // 4

def calculate_cost_inr(tokens: int, cost_per_million_usd: float) -> float:
    """Calculate cost in INR for given tokens"""
    cost_usd = (tokens / 1_000_000) * cost_per_million_usd
    cost_inr = cost_usd * USD_TO_INR
    return round(cost_inr, 4)

def initialize_csv_file():
    """Initialize CSV file with headers if it doesn't exist"""
    csv_path = Path(CSV_LOG_FILE)
    
    if not csv_path.exists():
        headers = [
            "Sno.", "Query", "Answer In your DB", "Embedding Token", 
            "Embedding Cost(INR)", "Input Token", "Input Cost(INR)", 
            "Output Token", "Output Cost(INR)", "Overall Query(INR)", "Timestamp"
        ]
        
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)
        logger.info(f"Initialized CSV file: {CSV_LOG_FILE}")
# important hai
def log_query_metrics(
    query: str,
    answer_found: bool,
    embedding_tokens: int,
    input_tokens: int,
    output_tokens: int,
    timestamp: str
):
    """Log query metrics to CSV file"""
    try:
        # Calculate costs
        embedding_cost = calculate_cost_inr(embedding_tokens, EMBEDDING_COST_PER_MILLION)
        input_cost = calculate_cost_inr(input_tokens, INPUT_COST_PER_MILLION)
        output_cost = calculate_cost_inr(output_tokens, OUTPUT_COST_PER_MILLION)
        total_cost = embedding_cost + input_cost + output_cost
        
        # Get next serial number
        csv_path = Path(CSV_LOG_FILE)
        sno = 1
        if csv_path.exists():
            with open(csv_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                rows = list(reader)
                if len(rows) > 1:  # More than just header
                    sno = len(rows)  # Next serial number
        
        # Prepare row data
        row_data = [
            sno,
            query[:100] + "..." if len(query) > 100 else query,  # Truncate long queries
            "Yes" if answer_found else "No",
            embedding_tokens,
            embedding_cost,
            input_tokens,
            input_cost,
            output_tokens,
            output_cost,
            round(total_cost, 4),
            timestamp
        ]
        
        # Append to CSV
        with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(row_data)
        
        logger.info(f"Logged query metrics: Total cost ₹{total_cost}")
        
    except Exception as e:
        logger.error(f"Failed to log query metrics: {e}")

# Initialize CSV file on startup
initialize_csv_file()

# use hai isme
def get_token_from_request(request: Request) -> str:
    """Extract JWT token from request headers"""
    authorization_header = request.headers.get("Authorization")
    if not authorization_header:
        raise HTTPException(
            status_code=401,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if it starts with 'Bearer '
    if not authorization_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format. Must be 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract token (remove 'Bearer ' prefix)
    token = authorization_header[7:]
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Token missing in authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return token

# yeh bhi jarurat hai iska
def verify_token_manual(token: str) -> dict:
    """Manually verify JWT token and extract token information"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        
        # Check if token is expired
        exp = payload.get("exp")
        if exp is None or datetime.utcnow() > datetime.fromtimestamp(exp):
            raise HTTPException(
                status_code=401,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        return {"exp": exp, "valid": True}
        
    except jwt.PyJWTError as e:
        logger.error(f"JWT verification failed: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Token verification error: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


# === FastAPI App ===
app = FastAPI(title="Combined RAG Service with JWT Authentication")


# Add CORS middleware for additional security configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this to specific domains in production
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# === Security Middleware ===
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# === Health Check Endpoint (No Authentication Required) ===
@app.get("/health")
async def health_check():
    """Health check endpoint - no authentication required"""
    return {"status": "healthy", "service": "Combined RAG Service"}


# === Authentication Test Endpoint ===
# yeh bhi jarurat hai iska
@app.post("/token")
async def login_for_access_token(form_data: TokenRequest):
    """Generate JWT token - requires admin credentials authentication"""
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token()
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


@app.post("/create_access_token")
async def create_access_token_endpoint():
    """Create access token endpoint - directly calls create_access_token()"""
    access_token = create_access_token()
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


####### Query Section ########


def calculate_similarity(text1: str, text2: str) -> float:
    """Calculate similarity between two texts using SequenceMatcher"""
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()


def filter_relevant_content(documents: List[str], metadatas: List[Dict], distances: List[float], query: str) -> tuple:
    """
    Filter documents to include only content that's potentially relevant to the query.
    This helps prevent mixing of unrelated case studies.
    """
    if not documents:
        return [], [], []
    
    # Extract key keywords from the query
    query_lower = query.lower()
    key_terms = []
    
    # Common business process terms that should be preserved
    business_terms = ['business process', 'automation', 'onboarding', 'dealer', 'customer', 'process', 'workflow', 'efficiency']
    
    # Extract specific nouns from the query
    words = re.findall(r'\b\w+\b', query_lower)
    
    # Add specific terms from query
    key_terms.extend([word for word in words if len(word) > 3])
    key_terms.extend(business_terms)
    
    filtered_docs = []
    filtered_metadatas = []
    filtered_distances = []
    
    for i, doc in enumerate(documents):
        doc_lower = doc.lower()
        
        # Count relevant term matches
        relevance_score = 0
        for term in key_terms:
            if term in doc_lower:
                relevance_score += 1
        
        # Keep documents that have at least some relevance or are from semantic search results
        # (semantic search should already be somewhat relevant)
        if relevance_score > 0 or len(key_terms) == 0:
            filtered_docs.append(doc)
            filtered_metadatas.append(metadatas[i] if i < len(metadatas) else {})
            filtered_distances.append(distances[i] if i < len(distances) else 0.0)
    
    logger.info(f"Content filtering: {len(documents)} -> {len(filtered_docs)} documents")
    return filtered_docs, filtered_metadatas, filtered_distances


def deduplicate_documents(documents: List[str], metadatas: List[Dict], distances: List[float], similarity_threshold: float = 0.8) -> tuple:
    """
    Deduplicate similar documents while preserving source information
    
    Args:
        documents: List of document texts
        metadatas: List of metadata dictionaries
        distances: List of distance scores
        similarity_threshold: Threshold for considering documents similar (0.8 = 80% similar)
    
    Returns:
        Tuple of (deduplicated_documents, merged_metadatas, distances)
    """
    if not documents:
        return [], [], []
    
    deduplicated_docs = []
    merged_metadatas = []
    final_distances = []
    processed_indices = set()
    
    for i, doc in enumerate(documents):
        if i in processed_indices:
            continue
            
        # Find all similar documents to this one
        similar_indices = [i]
        similar_sources = [metadatas[i].get('source_file', 'Unknown')]
        best_distance = distances[i]
        
        for j, other_doc in enumerate(documents):
            if j <= i or j in processed_indices:
                continue
                
            similarity = calculate_similarity(doc, other_doc)
            if similarity >= similarity_threshold:
                similar_indices.append(j)
                source_file = metadatas[j].get('source_file', 'Unknown')
                if source_file not in similar_sources:
                    similar_sources.append(source_file)
                # Keep the best (lowest) distance
                if distances[j] < best_distance:
                    best_distance = distances[j]
        
        # Mark all similar documents as processed
        for idx in similar_indices:
            processed_indices.add(idx)
        
        # Create merged metadata with all source files
        merged_metadata = metadatas[i].copy()
        if len(similar_sources) > 1:
            merged_metadata['source_files'] = similar_sources
            merged_metadata['merged_from_count'] = len(similar_sources)
            logger.info(f"Merged {len(similar_sources)} similar documents from sources: {similar_sources}")
        
        deduplicated_docs.append(doc)
        merged_metadatas.append(merged_metadata)
        final_distances.append(best_distance)
    
    logger.info(f"Deduplication: {len(documents)} -> {len(deduplicated_docs)} documents")
    return deduplicated_docs, merged_metadatas, final_distances


weaviate_client = weaviate.connect_to_weaviate_cloud(
    cluster_url=WEAVIATE_URL,
    auth_credentials=AuthApiKey(WEAVIATE_API_KEY),
    skip_init_checks=True,
)
# # Maximum retries for API calls
MAX_RETRIES = 3
RETRY_DELAY = 2
def query_with_retries(query_embedding, n_results):
    for attempt in range(MAX_RETRIES):
        try:
            # Initialize the Weaviate client
            client = weaviate.connect_to_weaviate_cloud(
                cluster_url=WEAVIATE_URL,
                auth_credentials=AuthApiKey(WEAVIATE_API_KEY),
                skip_init_checks=True  
            )
            
            # Access the collection
            collection = client.collections.get("Test")
            
            # Perform the query
            result = collection.query.near_vector(
                near_vector=query_embedding.tolist(),
                limit=n_results,
                return_metadata=MetadataQuery(distance=True)
            )
            return result
        
        except grpc._channel._InactiveRpcError:
            # Handle stale connection
            logger.warning("Stale connection detected. Reinitializing client...")
            time.sleep(RETRY_DELAY)  # Optional: Add a delay before retrying
            continue  # Retry the query
        
        except Exception as e:
            # Handle other exceptions
            logger.error(f"Query attempt {attempt + 1} failed: {str(e)}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)  # Add a delay before retrying
                continue
            raise e
async def generate_embedding1(text: str) -> tuple[np.ndarray, int]:
    """Generate embedding using Azure OpenAI and return embedding with token count"""
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
                
                # Get token usage from response
                token_count = response.usage.total_tokens if hasattr(response, 'usage') and response.usage else count_tokens(text)
                
                return np.array(response.data[0].embedding), token_count
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        return None, 0
async def generate_completion(prompt: str, system_prompt: str = None) -> tuple[str, int, int]:
    """Generate completion using Azure OpenAI and return response with token counts"""
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
                        return "", 0, 0
                    
                    content = response.choices[0].message.content.strip()
                    
                    # Get token usage from response
                    input_tokens = 0
                    output_tokens = 0
                    
                    if hasattr(response, 'usage') and response.usage:
                        input_tokens = response.usage.prompt_tokens
                        output_tokens = response.usage.completion_tokens
                    else:
                        # Fallback token counting
                        input_text = (system_prompt + " " + prompt) if system_prompt else prompt
                        input_tokens = count_tokens(input_text, CHAT_MODEL)
                        output_tokens = count_tokens(content, CHAT_MODEL)
 
                    return content, input_tokens, output_tokens
                finally:
                    await httpx_client.aclose()
 
    except Exception as e:
        logger.error(f"Error generating completion: {str(e)}")
        return "", 0, 0
 
 
@app.post("/query")
async def process_query(request: Request) -> Dict[str, Any]:
    try:
        logger.info("Received POST /query request")
        
        # === MANUAL TOKEN VERIFICATION ===
        # Step 1: Get token from request headers
        try:
            token = get_token_from_request(request)
            logger.info("Token extracted from request headers")
        except HTTPException as e:
            logger.warning(f"Token extraction failed: {e.detail}")
            raise e
        
        # Step 2: Verify the token
        try:
            current_user = verify_token_manual(token)
            logger.info("✅ Token verified successfully")
        except HTTPException as e:
            logger.warning(f"Token verification failed: {e.detail}")
            raise e
        
        # === TOKEN VERIFICATION COMPLETE - CONTINUE WITH QUERY ===
        logger.info(f"Authentication successful. Processing query for valid token")
        
        


        # Read and parse request body
        raw_body = await request.body()
        try:
            data = json.loads(raw_body.decode("utf-8").strip())
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON format: {e}")



        query = data.get("query")
        n_results = data.get("n_results", 10)
        similarity_threshold = data.get("similarity_threshold", 0.8)  # Default 80% similarity for deduplication
        enable_content_filtering = data.get("enable_content_filtering", True)  # Enable content filtering by default



        if not query:
            raise HTTPException(status_code=400, detail="Missing 'query' in request body.")



        logger.info(f"Generating embedding for query: {query}")



        # Step 1: Generate embedding using Azure OpenAI (with token tracking)
        query_embedding, embedding_tokens = await generate_embedding1(query)
        if query_embedding is None:
            raise HTTPException(status_code=500, detail="Failed to generate query embedding")



        # Step 2: Weaviate document retrieval
        logger.info("Sending query to Weaviate")



        try:
            # Use query_with_retries to handle retries
            result = query_with_retries(query_embedding, n_results)



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

            # === CONTENT FILTERING ===
            if enable_content_filtering:
                logger.info(f"Before content filtering: {len(documents)} documents")
                documents, metadatas, distances = filter_relevant_content(documents, metadatas, distances, query)
                logger.info(f"After content filtering: {len(documents)} documents")
            else:
                logger.info("Content filtering disabled")

            # === DEDUPLICATION LOGIC ===
            logger.info(f"Before deduplication: {len(documents)} documents")
            documents, metadatas, distances = deduplicate_documents(documents, metadatas, distances, similarity_threshold)
            logger.info(f"After deduplication: {len(documents)} documents")

            # Final check after filtering and deduplication
            if not documents:
                # Log query with no results found
                timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                log_query_metrics(
                    query=query,
                    answer_found=False,
                    embedding_tokens=embedding_tokens,
                    input_tokens=0,
                    output_tokens=0,
                    timestamp=timestamp
                )
                raise HTTPException(status_code=404, detail="No relevant documents found after filtering")



        except Exception as e:
            logger.error(f"Weaviate query failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to query Weaviate: {str(e)}")



        # Create numbered context for better reference mapping
        context_parts = []
        for i, doc in enumerate(documents):
            metadata = metadatas[i] if i < len(metadatas) else {}
            source_file = metadata.get('source_file', 'Unknown')
            file_type = metadata.get('file_type', 'unknown')
            context_parts.append(f"Document {i+1} (Source: {source_file}, Type: {file_type}):\n{doc}")
        
        context = "\n\n".join(context_parts)



        # Step 3: Generate answer using Azure OpenAI
        logger.info("Generating response using Azure OpenAI")



        system_prompt = """
        You are a helpful assistant that answers questions using only the provided context.
Each answer must be well-structured, grammatically correct, and include relevant details such as source slide number and source file.

🚨 CRITICAL CONSOLIDATION RULE 🚨
NEVER create multiple numbered points from the same source reference. If you find multiple insights from the same source (e.g., Reference 1), you MUST combine them into ONE single numbered point.

CRITICAL REQUIREMENTS:
1. Stay STRICTLY focused on the specific question asked - do not mix different case studies or topics
2. Each numbered point must represent a DIFFERENT source reference
3. If context contains multiple unrelated topics, only extract information relevant to the specific question
4. Extract meaningful, non-repetitive information from each context item
5. Use commas, periods, and proper sentence structure
6. Ensure each insight is unique and directly answers the question
7. If the context does not contain enough information to answer the specific question, respond with: "I don't have enough information to answer this question based on the context."
 
MANDATORY CONSOLIDATION LOGIC:
- Count the number of UNIQUE source references (Reference 1, Reference 2, etc.)
- Create EXACTLY that many numbered points - NO MORE
- If you have Reference 1, Reference 1, Reference 2 → Create only 2 points total
- If you have Reference 1, Reference 1, Reference 1 → Create only 1 point total
- If you have Reference 1, Reference 2, Reference 3 → Create 3 points total

RESPONSE FORMAT:
Provide your response as numbered points only (do NOT include "Answer:" label):

1. [Location Reference] ALL insights from Reference 1 combined into one comprehensive point. (Source: Reference 1)
2. [Location Reference] ALL insights from Reference 2 combined into one comprehensive point. (Source: Reference 2)

IMPORTANT FORMATTING RULES:
- Number each answer point (1., 2., 3., etc.) based on UNIQUE source references ONLY
- LOCATION REFERENCE RULES:
  * For PowerPoint files (.pptx): Use [Slide X] or [Slide X, Y] format
  * For Word documents (.docx): Use [Section X.X] format if section numbers are mentioned in content, otherwise omit brackets entirely
  * If unsure of file type: Omit bracketed references and start directly with content
- Add (Source: Reference N) at the end of each answer point where N corresponds to the document number
- Do NOT include a separate "Sources:" section in your response
- ABSOLUTE RULE: Each numbered point = One unique source reference, NO EXCEPTIONS
 
CONTENT RULES:
- If context mentions multiple different topics (e.g., dealer onboarding AND vehicle onboarding), only focus on the topic asked about
- Do not combine or mix information from different case studies unless they are directly related to the same question
- Each point should pass the test: "Does this directly answer the original question?"
- Discard any information that doesn't specifically relate to the question asked
 
Return only as many numbered points as there are UNIQUE sources with meaningful insights.
 
Only answer based on the provided context. Do not hallucinate or guess.
        """



        prompt = f"""Context:
        {context}

Question: {query}

IMPORTANT INSTRUCTIONS:
- Focus ONLY on information that directly relates to: "{query}"
- If the context contains multiple topics, extract ONLY the information relevant to the specific question asked
- Do not mix different case studies or topics in your response
- Each point should directly answer the question: "{query}"
- Ignore any information in the context that doesn't specifically relate to this question
- CHECK THE FILE TYPE in each document context:
  * If Type: pptx → Use [Slide X] format
  * If Type: docx → Do NOT use [Slide X] format; use [Section X.X] only if section numbers are mentioned in content, otherwise omit brackets
  * Never use slide references for Word documents

🚨 MANDATORY CONSOLIDATION INSTRUCTIONS 🚨
STEP 1: Count unique source references in the context (Reference 1, Reference 2, etc.)
STEP 2: Create EXACTLY that many numbered points - ONE point per unique source reference
STEP 3: Combine ALL insights from the same source reference into ONE comprehensive point

REQUIRED RESPONSE FORMAT (provide ONLY the numbered points, no labels):
1. [Appropriate Location Reference or None] ALL insights from Reference 1 combined together. (Source: Reference 1)
2. [Appropriate Location Reference or None] ALL insights from Reference 2 combined together. (Source: Reference 2)

CRITICAL EXAMPLES:
❌ WRONG: Two separate points for same source
1. [Slide 2.2] Clinical reference insight. (Source: Reference 1)
2. [Slide 2.2] CME credits insight. (Source: Reference 1)

✅ CORRECT for DOCX file: One combined point, no slide reference (since it's a Word document)
1. The medical sector includes clinical reference sources providing up-to-date medical information for healthcare professionals, and continuing medical education (CME) credits which are educational programs helping physician maintain licenses and stay current with medical advancements. (Source: Reference 1)

✅ CORRECT for PPTX file: One combined point with slide reference
1. [Slide 5, 7] The product features include automated workflows and real-time analytics across multiple presentation slides. (Source: Reference 1)

✅ CORRECT for DOCX with section numbers: One combined point with section reference if mentioned
1. [Section 2.2] The medical sector includes multiple professional-facing services as outlined in this section. (Source: Reference 1)

ABSOLUTE RULE: If both insights come from Reference 1, create only 1 numbered point total, not 2. Use appropriate location references based on file type.

Please answer the question based only on the provided context and follow this exact formatting structure."""



        try:
            llm_response, input_tokens, output_tokens = await generate_completion(prompt, system_prompt)
            if not llm_response:
                raise Exception("Empty response from Azure OpenAI")
            logger.info("LLM response generated successfully")
        except Exception as e:
            logger.error(f"Azure OpenAI generation failed: {str(e)}")
            traceback.print_exc()
            llm_response = f"I'm sorry, but I couldn't generate a response based on the provided context. Here are some relevant documents that might help answer your question about '{query}'."
            input_tokens = count_tokens(prompt + (system_prompt or ""), CHAT_MODEL)
            output_tokens = count_tokens(llm_response, CHAT_MODEL)
            logger.info("Using fallback response")



        # Create structured sources for the response with proper reference mapping
        sources = {}
        for i in range(len(documents)):
            metadata = metadatas[i] if i < len(metadatas) else {}
            
            # Extract source file information
            source_file = metadata.get('source_file', 'Unknown')
            
            # Handle merged sources
            if 'source_files' in metadata:
                source_info = f"Merged from {metadata['merged_from_count']} sources: {', '.join(metadata['source_files'])}"
                source_file = ', '.join(metadata['source_files'])
            else:
                source_info = source_file
            
            # Create reference key and entry
            reference_key = f"Reference {i + 1}"
            sources[reference_key] = {
                "reference_number": i + 1,
                "text": documents[i],
                "source_file": source_file,
                "source_info": f"Document {i + 1} (Source: {source_file})",
                "metadata": metadata,
                "relevance_score": 1.0 - distances[i] if i < len(distances) else 0
            }



        # Log successful query metrics
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        log_query_metrics(
            query=query,
            answer_found=True,  # We found documents and generated a response
            embedding_tokens=embedding_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            timestamp=timestamp
        )

        return {
            "answer": llm_response,
            "sources": sources
        }



    except Exception as e:
        logger.error(f"Exception occurred while processing query: {str(e)}")
        traceback.print_exc()
        
        # Log failed query if we have the query and embedding tokens
        try:
            if 'query' in locals() and 'embedding_tokens' in locals():
                timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                log_query_metrics(
                    query=query,
                    answer_found=False,
                    embedding_tokens=embedding_tokens if 'embedding_tokens' in locals() else 0,
                    input_tokens=0,
                    output_tokens=0,
                    timestamp=timestamp
                )
        except Exception as log_error:
            logger.error(f"Failed to log error query metrics: {log_error}")
        
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")
 
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)