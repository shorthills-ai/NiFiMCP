import sys
import json
from elasticsearch import Elasticsearch
import urllib3

# Disable SSL warnings for self-signed cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Static input for testing (replace with sys.stdin in production) ---
input_data = {
    "original_query": "{\"query\": \"python and nlp not django\"}",
    "boolean_query": "python and nlp not django"
}

# --- Elasticsearch Setup ---
client = Elasticsearch(
    "https://172.200.58.63:9200",
    api_key="bDhLS3haY0J5emY3NTkxU0s5ekQ6OW4tTkduaUpHb0VFQkhPLVh3blV1dw==",
    verify_certs=False
)

index_name = "hrbot2"

# --- Boolean Query Parser ---
def parse_boolean_query(query_str):
    query_str = query_str.upper().replace("AND", "&&").replace("OR", "||").replace("NOT", "!")
    tokens = query_str.split()

    must = []
    should = []
    must_not = []
    current_op = "AND"

    for token in tokens:
        if token == "&&":
            current_op = "AND"
        elif token == "||":
            current_op = "OR"
        elif token.startswith("!"):
            must_not.append(token[1:])
        else:
            if current_op == "AND":
                must.append(token)
            elif current_op == "OR":
                should.append(token)

    return must, should, must_not

# --- Main Logic ---
try:
    boolean_query = input_data.get("boolean_query", "").strip()
    if not boolean_query:
        raise ValueError("Missing 'boolean_query' in input.")

    must, should, must_not = parse_boolean_query(boolean_query)

    query_body = {"query": {"bool": {}}}
    if must:
        query_body["query"]["bool"]["must"] = [{"match": {"text": m}} for m in must]
    if should:
        query_body["query"]["bool"]["should"] = [{"match": {"text": s}} for s in should]
    if must_not:
        query_body["query"]["bool"]["must_not"] = [{"match": {"text": n}} for n in must_not]

    query_body["size"] = 100

    response = client.search(index=index_name, body=query_body)
    results = []

    for hit in response["hits"]["hits"]:
        results.append({
            "filename": hit["_source"].get("filename", "unknown"),
            "text": hit["_source"].get("text", "")
        })

    print(json.dumps({"results": results}, indent=2))

except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(1)
