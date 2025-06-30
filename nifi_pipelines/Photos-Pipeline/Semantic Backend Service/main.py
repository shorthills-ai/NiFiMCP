from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import json
import weaviate
from weaviate.classes.init import Auth
from openai import AzureOpenAI

# --- Load environment ---
load_dotenv()
WEAVIATE_URL = os.getenv("WEAVIATE_URL")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME")

# --- FastAPI App ---
app = FastAPI(title="Photos Pipeline Semantic Search", description="Search images via vector similarity in Weaviate")

# --- Weaviate Client (v4) ---
try:
    weaviate_client = weaviate.connect_to_weaviate_cloud(
        cluster_url=WEAVIATE_URL,
        auth_credentials=Auth.api_key(WEAVIATE_API_KEY)
    )
    print("✅ Connected to Weaviate Cloud (Weaviate Client v4)")
except Exception as e:
    print(f"❌ Failed to connect to Weaviate: {e}")
    raise RuntimeError(f"Could not connect to Weaviate: {e}")

# --- Azure OpenAI Client ---
azure_openai_client = AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    api_version="2024-12-01-preview",
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

# --- Input Schema ---
class QueryInput(BaseModel):
    query: str

# --- API Endpoint ---
@app.post("/semantic-query")
async def semantic_search(input: QueryInput):
    user_query = input.query.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    try:
        # Step 1: Get embedding from Azure OpenAI
        embedding_response = azure_openai_client.embeddings.create(
            input=user_query,
            model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME,
        )
        query_embedding = embedding_response.data[0].embedding

        # Step 2: Weaviate semantic search (v4 syntax)
        image_collection = weaviate_client.collections.get("image_search")
        
        response = image_collection.query.near_vector(
            near_vector=query_embedding,
            limit=5,
            return_properties=["image_path", "summary", "url"] # ONLY request properties that exist in your schema
        )

        # Step 3: Process results
        image_results = []

        for obj in response.objects:
            # Access properties directly from obj.properties
            summary = obj.properties.get("summary")
            image_url = obj.properties.get("url") 

            if image_url and summary: # Ensure both are present
                image_results.append({
                    "image_url": image_url,
                    "summary": summary
                })

        return {
            "query": user_query,
            "image_results": image_results,
            "message": f"Found {len(image_results)} matching images."
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")