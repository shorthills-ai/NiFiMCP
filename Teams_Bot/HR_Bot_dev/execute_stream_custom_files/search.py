import sys
import json
import openai
from openai import AzureOpenAI
from elasticsearch import Elasticsearch
import urllib3
from dotenv import load_dotenv
import os

load_dotenv()


# ------------------ Configuration ------------------

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version="2024-08-01-preview",
    azure_endpoint="https://us-tax-law-rag-demo.openai.azure.com"
)

EMBEDDING_DEPLOYMENT_NAME = "text-embedding-ada-002"
LLM_DEPLOYMENT_NAME = "gpt-4o"

# Elasticsearch config
es = Elasticsearch(
    "172.200.58.63:9200",
    api_key=os.getenv("ELASTICSEARCH_API_KEY"),
    verify_certs=True,
    ca_certs=""
)
index_name = "hrbot_embed"
# ------------------ Functions ------------------

def expand_query(query):
    system_prompt = (
        "You are a helpful assistant that rewrites search queries to make them more effective "
        "for semantic job matching. Expand the query by including related skills, tools, job titles, "
        "and common terminology. Respond with just one improved query string."
    )

    response = client.chat.completions.create(
        model=LLM_DEPLOYMENT_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Original search query: \"{query}\""}
        ],
        temperature=0.7,
        max_tokens=100
    )

    return response.choices[0].message.content.strip()


def get_embedding(query):
    response = client.embeddings.create(
        model=EMBEDDING_DEPLOYMENT_NAME,
        input=query
    )
    return response.data[0].embedding


def knn_search(embedding, score_threshold=0.90, top_k=15):
    response = es.search(
        index=index_name,
        size=top_k,
        knn={
            "field": "vector",
            "k": 50,
            "num_candidates": 1000,
            "query_vector": embedding
        },
        _source=["metadata.filename", "metadata.name"]
    )

    hits = response.get("hits", {}).get("hits", [])
    results = []

    for hit in hits:
        score = hit.get("_score", 0)
        if score >= score_threshold:
            employee_id = hit.get("_id", "")
            name = hit["_source"]["metadata"].get("name", "")
            results.append({
                "employee_id": employee_id,
                "name": name,
                "score": round(score, 4)
            })

    return results


# ------------------ Main ------------------

def main():
    try:
        input_data = sys.stdin.read()
        input_json = json.loads(input_data)
        query = input_json.get("query", "").strip()

        if not query:
            raise ValueError("Missing or empty 'query' key")

        expanded = expand_query(query)
        embedding = get_embedding(expanded)
        results = knn_search(embedding)

        print(json.dumps(results, ensure_ascii=False, indent=2))

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
