#!/usr/bin/env python3
import sys
import json
import requests
import warnings
from urllib3.exceptions import InsecureRequestWarning
from dotenv import load_dotenv
import os

# ✅ Load .env file from a specific path
load_dotenv(dotenv_path="/home/nifi/nifi2/HR_Bot/.env")


# Suppress SSL warnings
warnings.simplefilter('ignore', InsecureRequestWarning)


cert_path = os.getenv('ELASTIC_CA_CERT')
# Elasticsearch connection details
elastic_url = os.getenv('ELASTICSEARCH_URL2')
api_key = os.getenv("ELASTIC_API_KEY")

# Read keywords and job_description JSON from stdin
try:
    input_raw = sys.stdin.read()
    input_data = json.loads(input_raw)

    keywords = input_data.get("keywords", [])
    job_description = input_data.get("job_description", "")

    if not isinstance(keywords, list):
        raise ValueError("The 'keywords' field must be a list.")
except Exception as e:
    print(f"Error reading input from FlowFile: {e}", file=sys.stderr)
    sys.exit(1)

# Prepare Elasticsearch query
query = {
    "query": { "match_all": {} },
    "size": 1000
}
headers = {
    "Content-Type": "application/json",
    "Authorization": f"ApiKey {api_key}"
}

# Fetch and enrich resumes
try:
    response = requests.post(elastic_url, headers=headers, json=query, verify=cert_path)
    response.raise_for_status()

    hits = response.json().get("hits", {}).get("hits", [])
    if not hits:
        sys.exit(0)  # no results

    for hit in hits:
        resume = hit.get("_source", {})
        resume["keywords"] = keywords
        resume["job_description"] = job_description

        # Output as newline-separated JSON
        print(json.dumps(resume, separators=(",", ":")))
        print()

except requests.exceptions.RequestException as e:
    print(f"Error fetching resumes from Elasticsearch: {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"Unexpected error: {e}", file=sys.stderr)
    sys.exit(1)

