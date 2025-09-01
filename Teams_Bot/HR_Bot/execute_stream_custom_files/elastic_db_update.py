#!/usr/bin/env python3

import sys
import json
import traceback
import os
from dotenv import load_dotenv
from elasticsearch import Elasticsearch

# Load environment variables from .env
load_dotenv(dotenv_path="/home/nifi/nifi2/HR_Bot/.env")

class ResumeUpserter:
    def __init__(self, es_url, api_key, index_name, cert_path):
        self.client = Elasticsearch(
            es_url,
            api_key=api_key,
            verify_certs=True,
            ca_certs=cert_path
        )
        self.index = index_name

    def upsert_by_employee_id(self, employee_id, document):
        try:
            # Index (acts as insert or replace)
            response = self.client.index(
                index=self.index,
                id=str(employee_id),
                document=document
            )

            output = {
                "status": "success",
                "employee_id": employee_id,
                "document_id": response["_id"],
                "result": response.get("result", "unknown")
            }
            print(json.dumps(output))
            sys.exit(0)

        except Exception as e:
            error_output = {
                "status": "error",
                "employee_id": employee_id,
                "message": str(e)
            }
            print(json.dumps(error_output), file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            sys.exit(1)


def main():
    try:
        input_data = json.loads(sys.stdin.read())
        employee_id = input_data.get("employee_id")
    except json.JSONDecodeError:
        print("❌ Invalid JSON input", file=sys.stderr)
        sys.exit(1)

    if not employee_id:
        print("❌ No employee_id provided in input.", file=sys.stderr)
        sys.exit(1)

    # Elasticsearch config from .env
    es_url = os.getenv("ELASTICSEARCH_URL")
    api_key = os.getenv("ELASTIC_API_KEY")
    index_name = "hrbot"
    cert_path = os.getenv("ELASTIC_CA_CERT")

    upserter = ResumeUpserter(es_url, api_key, index_name, cert_path)
    upserter.upsert_by_employee_id(employee_id, input_data)


if __name__ == "__main__":
    main()
