from elasticsearch import Elasticsearch
import json
import sys

# Step 1: Read input JSON from stdin (useful when run from NiFi's ExecuteScript or an HTTP endpoint)
input_json = sys.stdin.read()
data = json.loads(input_json)

# Step 2: Extract the vector
query_vector = data.get("query_vector")

# Step 3: Validate vector length
if not query_vector or len(query_vector) != 1536:
    raise ValueError("Invalid query_vector: Must be a list of 1536 float values.")

# Step 4: Initialize Elasticsearch client
client = Elasticsearch(
    "https://22f11ab875944bd2982501e7639c5c0f.us-central1.gcp.cloud.es.io:443",
    api_key="d1RPa2dwY0J5Y09JTFFVaDJhaU06WlpDbW91a21PWFZxcTdfYWxOUksydw=="
)

# Step 5: Perform vector search using cosine similarity
response = client.search(index="hrbot", body={
    "size": 5,
    "query": {
        "script_score": {
            "query": {"match_all": {}},
            "script": {
                "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                "params": {
                    "query_vector": query_vector
                }
            }
        }
    }
})

# Step 6: Display results
for hit in response["hits"]["hits"]:
    print(f"Score: {hit['_score']}")
    print(f"Filename: {hit['_source'].get('filename')}")
    print(f"Text: {hit['_source'].get('text')}")
    print("-" * 50)
