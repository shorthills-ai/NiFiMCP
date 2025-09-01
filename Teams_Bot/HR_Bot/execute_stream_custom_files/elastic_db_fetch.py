#!/usr/bin/env python3

import json
import sys
import os
from dotenv import load_dotenv
from elasticsearch import Elasticsearch, NotFoundError

# Load environment variables
load_dotenv(dotenv_path="/home/nifi/nifi2/HR_Bot/.env")

# Get config from environment
ES_URL = os.getenv("ELASTICSEARCH_URL")
ES_API_KEY = os.getenv("ELASTIC_API_KEY")
ES_CA_CERT = os.getenv("ELASTIC_CA_CERT")
ES_INDEX_NAME = "hrbot"

# Fail early if required vars are missing
for var in ["ELASTICSEARCH_URL", "ELASTIC_API_KEY", "ELASTIC_CA_CERT"]:
    if not os.getenv(var):
        sys.stderr.write(f"❌ Missing required environment variable: {var}\n")
        sys.exit(1)

# Setup Elasticsearch client
client = Elasticsearch(
    ES_URL,
    api_key=ES_API_KEY,
    verify_certs=True,
    ca_certs=ES_CA_CERT
)

def get_existing_fields(employee_id, index_name=ES_INDEX_NAME):
    try:
        res = client.get(index=index_name, id=str(employee_id))
        return res["_source"]  # Return the full document
    except NotFoundError:
        return {}  # No existing data
    except Exception as e:
        sys.stderr.write(f"Elasticsearch error: {str(e)}\n")
        return {}

def extract_new_fields(input_json):
    # Extract and clean skills field
    raw_skills = input_json.get(
        "Skills(Comma separated)  \nEg. Python, NLP, HTML, CSS ............", ""
    )
    skills = [s.strip() for s in raw_skills.split(",") if s.strip()]

    # Extract raw projects field
    projects_raw = input_json.get(
        "Projects\nEg.\n\nProject1 title(Month/YYYY): Project1 description \nProject2 title(Month/YYYY): Project2 description  ",
        ""
    ).strip()

    return {
        "skills": skills,
        "projects": projects_raw
    }

def main():
    try:
        # Load input JSON from stdin
        excel_json = json.load(sys.stdin)

        # Extract identifiers
        employee_id = excel_json.get("Employee id")
        employee_name = excel_json.get("Employee Name", "").strip()

        if not employee_id:
            raise ValueError("Employee id missing")

        # Extract new fields from Excel JSON
        new_data = extract_new_fields(excel_json)

        # Fetch full existing document from Elasticsearch
        existing_data = get_existing_fields(employee_id)

        # Combine results
        result = {
            "employee_id": employee_id,
            "employee_name": employee_name,
            "new_data": new_data,
            "existing_data": existing_data
        }

        # Output result
        print(json.dumps(result, indent=2))

    except Exception as e:
        sys.stderr.write(f"Processing error: {str(e)}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
