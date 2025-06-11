import os
import json
import boto3
import requests
import numpy as np
from typing import List, Optional
from dotenv import load_dotenv
import asyncio
import sys

from openai import AsyncOpenAI, AsyncAzureOpenAI, OpenAIError

# Load environment variables
load_dotenv()

class Embedder:
    def __init__(self):
        self.provider = os.getenv("EMBEDDING_PROVIDER").lower()
        # print("provider:", self.provider)
        self.model = os.getenv("EMBEDDING_MODEL")
        # print("model:", self.model)
        # print("provider:", self.provider)

        if self.provider == "openai":
            self.api_key = os.getenv("OPENAI_API_KEY")

        elif self.provider == "azure":
            # print("Using Azure OpenAI")
            self.api_key = os.getenv("AZURE_OPENAI_KEY")
            # print("Azure API Key:", self.api_key)
            self.endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            self.api_version = os.getenv("AZURE_OPENAI_API_VERSION")
            self.model = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL")

        elif self.provider == "huggingface":
            self.api_key = os.getenv("HUGGINGFACE_API_KEY")

        elif self.provider == "aws":
            self.provider = os.getenv("EMBEDDING_PROVIDER", "aws").lower()
            self.aws_model = os.getenv("AWS_EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0")
            self.region = os.getenv("AWS_REGION", "us-west-2")
            self.bedrock = boto3.client("bedrock-runtime", region_name=self.region)

        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    async def get_embedding(self, texts: List[str], model: Optional[str] = None) -> List[List[float]]:
        model =  self.model

        # if self.provider == "openai":
        #     model=os.getenv("EMBEDDING_MODEL")
        #     print(f"Using OpenAI with model: {model}")
        #     return await self._openai_embedding(texts, model)
        if self.provider == "azure":
            model=os.getenv("EMBEDDING_MODEL")
            # print(f"Using Azure OpenAI with model: {model}")
            return await self._azure_openai_embedding(texts, model)
        # elif self.provider == "huggingface":
        #     model=os.getenv("EMBEDDING_MODEL")
        #     print(f"Using Hugging Face with model: {model}")
        #     return self._huggingface_embedding(texts, model)
        elif self.provider == "aws":
            model=os.getenv("EMBEDDING_MODEL")
            # print(f"Using AWS Bedrock with model1222: {model}")
            return self._aws_embedding(texts, model)
        else:
            raise ValueError("Invalid provider.")

    async def _azure_openai_embedding(self, texts: List[str], model: str) -> List[List[float]]:
        # print(f"Using Azure OpenAI with model: {model}")
        # print(f"Azure Endpoint: {self.endpoint}, API Key: {self.api_key}, API Version: {self.api_version}")
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


    async def _openai_embedding(self, texts: List[str], model: str) -> List[List[float]]:
        try:
            client = AsyncOpenAI(api_key=self.api_key)
            response = await client.embeddings.create(
                model=model,
                input=texts,
                encoding_format="float"
            )
            return [res.embedding for res in response.data]
        except Exception as e:
            print(f"OpenAI error: {e}")
            return []

    def _huggingface_embedding(self, texts: List[str], model: str) -> List[List[float]]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{model}"
        response = requests.post(url, headers=headers, json={"inputs": texts})
        response.raise_for_status()
        return response.json()

    def _aws_embedding(self, texts: List[str], model: str) -> List[List[float]]:
        print(f"Using AWS Bedrock with model: {model}")
        body = {
        "inputText": texts[0]  # Titan currently accepts one input at a time
        }

        response = self.bedrock.invoke_model(
        modelId=self.model,
        body=json.dumps(body).encode("utf-8"),
        contentType="application/json",
        accept="application/json"
        )
        response_body = response["body"].read().decode("utf-8")
        # print(f"Response from AWS Bedrock: {response_body}")
        return [json.loads(response_body)["embedding"]]


# ----------- NiFi Input Handler -----------

def main():
    try:
        # Read input from stdin (NiFi sends file content here)
        input_text = sys.stdin.read().strip()
        # input_text = "Hi my name is priyanshu singh i have 10 years of experience of coding"

        embedder = Embedder()
        # print(f"Input text: {input_text}")
        embedding = asyncio.run(embedder.get_embedding([input_text]))
        # print(f"Generated embedding: {embedding}")
        # print(json.dumps({"embedding": embedding}))

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
