import sys
import json
import openai
from openai import AzureOpenAI
from elasticsearch import Elasticsearch
from datetime import datetime
import urllib3

# ------------------ Configuration ------------------

client = AzureOpenAI(
    api_key="AZURE_OPENAI_API_KEY",
    api_version="AZURE_OPENAI_API_VERSION",
    azure_endpoint="AZURE_OPENAI_ENDPOINT"
)

EMBEDDING_DEPLOYMENT_NAME = "text-embedding-ada-002"
LLM_DEPLOYMENT_NAME = "gpt-4o"

# Elasticsearch config
es = Elasticsearch(
    "https://172.200.58.63:9200",
    api_key="ES_API_KEY",
    verify_certs=True,
    ca_certs=cert_path
)

index_name = "hrbot_embed"

# ------------------ LLM Usage Logger ------------------

class LLMUsageLogger:
    def __init__(self, deployment_name, log_path):
        self.deployment_name = deployment_name
        self.log_path = log_path
        self.input_cost_per_1k = 0.000165
        self.output_cost_per_1k = 0.000660

    def log(self, response, prompt_type):
        try:
            usage = getattr(response, 'usage', None)
            if not usage:
                return  # Embedding endpoint often lacks token usage

            prompt_tokens = usage.prompt_tokens
            completion_tokens = usage.completion_tokens
            input_cost = (prompt_tokens / 1000) * self.input_cost_per_1k
            output_cost = (completion_tokens / 1000) * self.output_cost_per_1k
            total_cost = input_cost + output_cost

            timestamp = datetime.now().isoformat()
            log_line = (
                f"LLM_USAGE | {timestamp} | "
                f"model={self.deployment_name} | type={prompt_type} | "
                f"prompt_tokens={prompt_tokens} | completion_tokens={completion_tokens} | "
                f"total_cost=${total_cost:.6f}"
            )

            with open(self.log_path, "a") as f:
                f.write(log_line + "\n")

        except Exception as e:
            print(f"LLM_USAGE_LOG_ERROR: {e}", file=sys.stderr)

logger = LLMUsageLogger(
    deployment_name=LLM_DEPLOYMENT_NAME,
    log_path="/home/nifi/nifi2/users/HR_Teams_Bot_Dev/llm_usage.log"
)

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

    logger.log(response, prompt_type="search")
    return response.choices[0].message.content.strip()


def get_embedding(query):
    response = client.embeddings.create(
        model=EMBEDDING_DEPLOYMENT_NAME,
        input=query
    )

    # Optional: could log embedding token usage if desired
    # logger.log(response, prompt_type="search")

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
