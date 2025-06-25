import os
import json
import boto3
import requests
from typing import List, Optional
from dotenv import load_dotenv
import asyncio
import sys

from openai import AsyncOpenAI, AsyncAzureOpenAI

# Load environment variables
load_dotenv()

class Embedder:
    def __init__(self):
        self.provider = os.getenv("EMBEDDING_PROVIDER").lower()
        self.model = os.getenv("EMBEDDING_MODEL")

        if self.provider == "openai":
            self.api_key = os.getenv("OPENAI_API_KEY")

        elif self.provider == "azure":
            self.api_key = os.getenv("AZURE_OPENAI_KEY")
            self.endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            self.api_version = os.getenv("AZURE_OPENAI_API_VERSION")
            self.model = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL")

        elif self.provider == "huggingface":
            self.api_key = os.getenv("HUGGINGFACE_API_KEY")

        elif self.provider == "aws":
            self.aws_model = os.getenv("AWS_EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0")
            self.region = os.getenv("AWS_REGION", "us-west-2")
            self.bedrock = boto3.client("bedrock-runtime", region_name=self.region)

        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    async def get_embedding(self, texts: List[str], model: Optional[str] = None) -> List[List[float]]:
        model = self.model

        if self.provider == "azure":
            return await self._azure_openai_embedding(texts, model)
        elif self.provider == "aws":
            return self._aws_embedding(texts, model)
        else:
            raise ValueError("Invalid provider.")

    async def _azure_openai_embedding(self, texts: List[str], model: str) -> List[List[float]]:
        try:
            client = AsyncAzureOpenAI(
                azure_endpoint=self.endpoint,
                api_key=self.api_key,
                api_version=self.api_version
            )

            response = await client.embeddings.create(
                model=model,
                input=texts,
                encoding_format="float"
            )
            return [res.embedding for res in response.data]

        except Exception as e:
            print(f"Azure OpenAI embedding error: {e}")
            return []

    def _aws_embedding(self, texts: List[str], model: str) -> List[List[float]]:
        body = {
            "inputText": texts[0]
        }

        response = self.bedrock.invoke_model(
            modelId=self.model,
            body=json.dumps(body).encode("utf-8"),
            contentType="application/json",
            accept="application/json"
        )
        response_body = response["body"].read().decode("utf-8")
        return [json.loads(response_body)["embedding"]]


# ----------- NiFi Input Handler -----------

def main():
    try:
        # Read input JSON from stdin
        input_data = sys.stdin.read().strip()
        parsed_input = json.loads(input_data)

        filename = parsed_input.get("filename", "unknown.txt")
        input_text = parsed_input.get("text", "")

        embedder = Embedder()
        embedding = asyncio.run(embedder.get_embedding([input_text]))

        output = {
            "filename": filename,
            "text": input_text,
            "embedding": embedding[0]
        }

        # Pretty JSON: each field on a new line, embedding array in one line
        print(
            '{\n'
            f'  "filename": "{output["filename"]}",\n'
            f'  "text": {json.dumps(output["text"])},\n'
            f'  "embedding": {json.dumps(output["embedding"])}\n'
            '}'
        )

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
