import sys
import json
import requests
import warnings
from urllib3.exceptions import InsecureRequestWarning
from dotenv import load_dotenv
import os

# ✅ Load .env file from current directory
load_dotenv()


warnings.simplefilter('ignore', InsecureRequestWarning)

def fetch_resume(identifier_type, identifier):
    """
    Fetches a resume from Elasticsearch based on the identifier type and value.
    """
    cert_path=os.environ.get('CERT_PATH')
# Elasticsearch connection details
    elastic_url = os.environ.get('ELASTIC_URL')
    api_key = os.environ.get("ELASTIC_API")

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
        # Read keywords from stdin
        keywords_input = sys.stdin.read()
        keywords_data = json.loads(keywords_input)
        keywords = keywords_data.get("keywords", [])
        if not isinstance(keywords, list):
            raise ValueError("The 'keywords' field must be a list.")

        # Get identifier from the same input
        identifier_type = keywords_data.get("identifier_type")
        identifier = keywords_data.get("identifier")

        if not identifier_type or not identifier:
            print(json.dumps({"error": "Missing identifier_type or identifier"}), file=sys.stderr)
            sys.exit(1)

        # Fetch the specific resume
        resume = fetch_resume(identifier_type, identifier)

        if resume:
            # Add keywords to the resume
            resume["keywords"] = keywords
            print(json.dumps(resume, separators=(",", ":")))

    except json.JSONDecodeError:
        print(json.dumps({"error": "Invalid JSON input"}), file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": f"An unexpected error occurred: {e}"}), file=sys.stderr)
        sys.exit(1)
