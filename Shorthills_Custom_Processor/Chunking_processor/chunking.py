import os
import re
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Literal
from dotenv import load_dotenv
import uvicorn
import sys

# Load environment variables
load_dotenv()

AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
CHUNK_TYPE=os.getenv("CHUNK_TYPE", "fixed").lower()
CHUNK_SIZE=int(os.getenv("CHUNK_SIZE", 500))

app = FastAPI()

# ---------- Data Models ----------

class ChunkRequest(BaseModel):
    text: str
    chunk_type: Literal["fixed", "recursive", "semantic", "hybrid"]
    chunk_size: int = 500

class ChunkResponse(BaseModel):
    chunks: List[str]
    total_chunks: int

# ---------- Chunking Methods ----------

def fixed_chunking(text: str, size: int) -> List[str]:
    return [text[i:i + size] for i in range(0, len(text), size)]

def recursive_chunking(text: str, size: int) -> List[str]:
    paragraphs = re.split(r'\n{2,}', text)
    result = []
    for para in paragraphs:
        if len(para) <= size:
            result.append(para)
        else:
            sentences = re.split(r'(?<=[.!?]) +', para)
            for sentence in sentences:
                if len(sentence) <= size:
                    result.append(sentence)
                else:
                    words = sentence.split()
                    for i in range(0, len(words), size):
                        result.append(" ".join(words[i:i + size]))
    return result

def semantic_chunking(text: str, size: int) -> List[str]:
    sentences = re.split(r'(?<=[.!?]) +', text)
    chunks = []
    buffer = ""

    for sentence in sentences:
        if len(buffer) + len(sentence) <= size:
            buffer += sentence + " "
        else:
            chunks.append(buffer.strip())
            buffer = sentence + " "
    if buffer.strip():
        chunks.append(buffer.strip())
    return chunks

def hybrid_chunking(text: str, size: int) -> List[str]:
    sem_chunks = semantic_chunking(text, size * 2)
    final_chunks = []
    for chunk in sem_chunks:
        final_chunks.extend(fixed_chunking(chunk, size))
    return final_chunks

# ---------- FastAPI Endpoint ----------

# @app.post("/chunk", response_model=ChunkResponse)
# def chunk_text(req: ChunkRequest):
#     if req.chunk_size <= 0:
#         raise HTTPException(status_code=400, detail="chunk_size must be > 0")

#     try:
#         if req.chunk_type == "fixed":
#             chunks = fixed_chunking(req.text, req.chunk_size)
#         elif req.chunk_type == "recursive":
#             chunks = recursive_chunking(req.text, req.chunk_size)
#         elif req.chunk_type == "semantic":
#             chunks = semantic_chunking(req.text, req.chunk_size)
#         elif req.chunk_type == "hybrid":
#             chunks = hybrid_chunking(req.text, req.chunk_size)
#         else:
#             raise HTTPException(status_code=400, detail="Invalid chunk type.")
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

#     return ChunkResponse(chunks=chunks, total_chunks=len(chunks))

# if __name__ == "__main__":
#     port = int(os.environ.get("PORT", 8000))
#     uvicorn.run(app, host="0.0.0.0", port=port)

def main():
    try:
        # Read input from stdin (NiFi sends file content here)
        input_text = sys.stdin.read().strip()
        # input_text = "Hi my name is priyanshu singh i have 10 years of experience of coding"
        if CHUNK_TYPE == "fixed":
             print(f"Using fixed chunking with size: {CHUNK_SIZE}")
             chunks = fixed_chunking(input_text, CHUNK_SIZE)
             print(chunks)
        elif CHUNK_TYPE == "recursive":
            print(f"Using recursive chunking with size: {CHUNK_SIZE}")
            chunks = recursive_chunking(input_text, CHUNK_SIZE)
            print(chunks)
        elif CHUNK_TYPE == "semantic":
            print(f"Using semantic chunking with size: {CHUNK_SIZE}")
            chunks = semantic_chunking(input_text, CHUNK_SIZE)
            print(chunks)
        elif CHUNK_TYPE == "hybrid":
            print(f"Using hybrid chunking with size: {CHUNK_SIZE}")
            chunks = hybrid_chunking(input_text, CHUNK_SIZE)
            print(chunks)
        else:
            raise HTTPException(status_code=400, detail="Invalid chunk type.")
        

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()