import sys
import json
import requests
from dotenv import load_dotenv
import os
import base64

load_dotenv()

# Read the FlowFile content from stdin
input_data = json.loads(sys.stdin.read().strip())
query = input_data.get("query")

if not query:
    print(json.dumps({"error": "No query provided"}))
    sys.exit(1)

# Configurations for Elastic Cloud
es_host = os.getenv("ES_HOST", "https://22f11ab875944bd2982501e7639c5c0f.us-central1.gcp.cloud.es.io:443")
es_index = os.getenv("ES_INDEX", "hrbot")
es_api_key = os.getenv("ES_API_KEY", "d1RPa2dwY0J5Y09JTFFVaDJhaU06WlpDbW91a21PWFZxcTdfYWxOUksydw==")

# Elasticsearch query
es_query = {
    "query": {
        "match": {
            "text": query
        }
    }
}

headers = {
    "Content-Type": "application/json",
    "Authorization": f"ApiKey {es_api_key}"
}

try:
    response = requests.post(
        f"{es_host}/{es_index}/_search",
        headers=headers,
        json=es_query
    )
    response.raise_for_status()
    hits = response.json().get("hits", {}).get("hits", [])
    results = [{"filename": hit["_source"].get("filename", "unknown"), "text": hit["_source"].get("text", "")} for hit in hits]

    print(json.dumps({"results": results}, indent=2))

except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(1)
