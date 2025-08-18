import sys
import json
import requests
from dotenv import load_dotenv
import os

# ✅ Load .env file from a specific path
load_dotenv( )


def fetch_resume(identifier_type, identifier):
    """
    Fetches a resume from Elasticsearch based on the identifier type and value.
    """
    cert_path = os.getenv('ELASTIC_CA_CERT')
# Elasticsearch connection details
    elastic_url = os.getenv('ELASTICSEARCH_URL2')
    api_key = os.getenv("ELASTIC_API_KEY")


    headers = {
        "Content-Type": "application/json",
        "Authorization": f"ApiKey {api_key}"
    }

    query = {
        "query": {
            "match": {
                identifier_type: identifier
            }
        }
    }

    try:
        response = requests.post(elastic_url, headers=headers, json=query,verify=cert_path)
        response.raise_for_status()  # Raise an exception for bad status codes
        data = response.json()
        if "hits" in data and "hits" in data["hits"] and data["hits"]["hits"]:
            return data["hits"]["hits"][0]["_source"]
        return {}
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}

if __name__ == "__main__":
    try:
        input_data = json.load(sys.stdin)
        identifier_type = input_data.get("identifier_type")
        identifier = input_data.get("identifier")

        if not identifier_type or not identifier:
            print(json.dumps({"error": "Missing identifier_type or identifier"}), file=sys.stderr)
            sys.exit(1)

        result = fetch_resume(identifier_type, identifier)
        print(json.dumps(result))

    except json.JSONDecodeError:
        print(json.dumps({"error": "Invalid JSON input"}), file=sys.stderr)
        sys.exit(1)
