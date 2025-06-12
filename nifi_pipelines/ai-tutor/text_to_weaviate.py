import os
import sys
import logging
import argparse
from typing import List, Dict
import weaviate
from weaviate.auth import AuthApiKey
from weaviate.exceptions import WeaviateBaseError
from weaviate.classes.config import DataType
import uuid
from dotenv import load_dotenv
import tiktoken
from pathlib import Path
import asyncio
import atexit
import warnings
from openai import AsyncOpenAI
import httpx
from aiohttp import ClientSession

# Suppress specific SSL warnings
warnings.filterwarnings('ignore', category=ResourceWarning)

# Configure logging to write to stderr for NiFi
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

class TextChunker:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.tokenizer = tiktoken.get_encoding("cl100k_base")

    def split_text(self, text: str) -> List[str]:
        """Split text into chunks with overlap."""
        tokens = self.tokenizer.encode(text)
        chunks = []
        
        for i in range(0, len(tokens), self.chunk_size - self.chunk_overlap):
            chunk_tokens = tokens[i:i + self.chunk_size]
            chunk_text = self.tokenizer.decode(chunk_tokens)
            chunks.append(chunk_text)
            
        return chunks

class WeaviateIndexer:
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Get Weaviate credentials from environment variables
        self.weaviate_url = os.getenv("WEAVIATE_URL")
        self.weaviate_api_key = os.getenv("WEAVIATE_API_KEY")
        self.embedding_dimensions = int(os.getenv("WEAVIATE_EMBEDDING") or 768)
        
        if not all([self.weaviate_url, self.weaviate_api_key]):
            raise ValueError("Weaviate credentials not found in environment variables")
        
        # Ensure URL has https:// scheme
        if not self.weaviate_url.startswith(('http://', 'https://')):
            self.weaviate_url = f"https://{self.weaviate_url}"
        
        # Initialize Weaviate client
        self.client = self._get_client()
        self._setup_schema()
        
        # OpenAI client setup
        self.openai_client = None
        self.httpx_client = None
        self.session = None

    async def cleanup_async(self):
        """Async cleanup of resources."""
        try:
            if self.session and not self.session.closed:
                await self.session.close()
            if self.httpx_client and not self.httpx_client.is_closed:
                await self.httpx_client.aclose()
        except Exception as e:
            logger.warning(f"Error during async cleanup: {str(e)}")

    def cleanup(self):
        """Cleanup resources."""
        if hasattr(self, 'client'):
            self.client.close()
        # Run async cleanup in event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, create a new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(self.cleanup_async())
        except Exception as e:
            logger.warning(f"Error during cleanup: {str(e)}")
        finally:
            try:
                loop.close()
            except Exception as e:
                logger.warning(f"Error closing event loop: {str(e)}")

    def _get_client(self):
        """Initialize and return Weaviate client."""
        try:
            client = weaviate.connect_to_weaviate_cloud(
                cluster_url=self.weaviate_url,
                auth_credentials=AuthApiKey(self.weaviate_api_key),
                skip_init_checks=True
            )

            if not client.is_ready():
                raise WeaviateBaseError("Client is not ready")
            
            logger.info("✅ Successfully connected to Weaviate Cloud!")
            return client

        except WeaviateBaseError as e:
            logger.error(f"Failed to connect to Weaviate Cloud: {e}")
            raise

    def _setup_schema(self):
        """Set up the Weaviate schema if it doesn't exist."""
        try:
            existing_collections = self.client.collections.list_all()
            
            if "Document" not in existing_collections:
                self.client.collections.create(
                    name="Document",
                    properties=[
                        {"name": "content", "data_type": DataType.TEXT},
                        {"name": "chunk_index", "data_type": DataType.INT},
                        {"name": "source_file", "data_type": DataType.TEXT}
                    ],
                    vectorizer_config=None
                )
                logger.info("Schema created successfully")
        except Exception as e:
            logger.error(f"Error setting up schema: {str(e)}")
            raise

    async def get_embedding(self, text: str) -> List[float]:
        """Get embeddings from OpenAI."""
        try:
            if not self.openai_client or not self.httpx_client:
                self.session = ClientSession()
                self.httpx_client = httpx.AsyncClient()
                self.openai_client = AsyncOpenAI(
                    api_key=os.getenv("OPENAI_API_KEY"),
                    http_client=self.httpx_client
                )

            response = await self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=text,
                encoding_format="float"
            )

            if not response or not hasattr(response, "data") or not response.data:
                logger.error("Empty or invalid response from OpenAI embedding API")
                return []

            return response.data[0].embedding

        except Exception as e:
            logger.error(f"Error getting embedding from OpenAI: {str(e)}")
            raise

    async def index_chunks(self, chunks: List[str], source_file: str):
        """Index chunks to Weaviate."""
        try:
            for i, chunk in enumerate(chunks):
                embedding = await self.get_embedding(chunk)
                
                data_object = {
                    "content": chunk,
                    "chunk_index": i,
                    "source_file": source_file
                }
                
                self.client.collections.get("Document").data.insert(
                    properties=data_object,
                    vector=embedding,
                    uuid=str(uuid.uuid4())
                )
                
                logger.info(f"Indexed chunk {i+1}/{len(chunks)} from {source_file}")
        except Exception as e:
            logger.error(f"Error indexing chunks: {str(e)}")
            raise

async def process_stdin(chunker: TextChunker, indexer: WeaviateIndexer, source_name: str):
    """Process input from stdin."""
    try:
        # Read content from stdin
        text = sys.stdin.read()
        if not text:
            logger.error("No content received from stdin")
            print("Error: No content received from stdin", file=sys.stdout)
            return False

        # Split text into chunks
        chunks = chunker.split_text(text)
        logger.info(f"Split input into {len(chunks)} chunks")
        
        # Index chunks to Weaviate
        await indexer.index_chunks(chunks, source_name)
        logger.info(f"Successfully indexed content from {source_name}")
        
        # Write success message to stdout for NiFi
        print(f"Successfully processed content from {source_name}", file=sys.stdout)
        return True
        
    except Exception as e:
        logger.error(f"Error processing stdin: {str(e)}")
        print(f"Error processing content: {str(e)}", file=sys.stdout)
        return False

async def main_async():
    parser = argparse.ArgumentParser(description='Process text content and index it to Weaviate')
    parser.add_argument('--source-name', type=str, required=True, help='Source name for the content (e.g., S3 object key)')
    args = parser.parse_args()

    # Load environment variables
    load_dotenv()
    
    # Initialize components
    chunker = TextChunker()
    indexer = WeaviateIndexer()
    
    try:
        # Process stdin input
        success = await process_stdin(chunker, indexer, args.source_name)
        # Cleanup before exiting
        await indexer.cleanup_async()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Error in main process: {str(e)}")
        print(f"Error processing content: {str(e)}", file=sys.stderr)
        sys.exit(1)

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\nProcess interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 