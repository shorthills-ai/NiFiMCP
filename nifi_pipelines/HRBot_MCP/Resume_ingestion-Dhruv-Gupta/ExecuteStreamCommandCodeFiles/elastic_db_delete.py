#!/usr/bin/env python3

import sys
import json
import traceback
from elasticsearch import Elasticsearch, NotFoundError
from elasticsearch import exceptions as es_exceptions
from dotenv import load_dotenv
import os

# ✅ Load .env file from current directory
load_dotenv()



class ResumeDeleter:
    def __init__(self, es_url, api_key, index_name, cert_path):
        try:
            self.client = Elasticsearch(
                es_url,
                api_key=api_key,
                verify_certs=True,
                ca_certs=cert_path,
                request_timeout=10
            )
            self.index = index_name
        except Exception as e:
            print(json.dumps({
                "status": "cert_error",
                "message": f"Certificate or connection error: {str(e)}"
            }), file=sys.stderr)
            sys.exit(1)

    def delete_by_employee_id(self, employee_id):
        doc_id = f"{employee_id}"
        try:
            response = self.client.delete(index=self.index, id=doc_id)
            return {
                "status": "success",
                "employee_id": employee_id,
                "index": self.index,
                "result": response.get("result", "unknown")
            }
        except NotFoundError:
            return {
                "status": "not_found",
                "employee_id": employee_id,
                "index": self.index
            }
        except es_exceptions.ElasticsearchException as e:

            return {
                "status": "error",
                "employee_id": employee_id,
                "index": self.index,
                "message": str(e)
            }

def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(json.dumps({"error": "Invalid JSON input", "detail": str(e)}), file=sys.stderr)
        sys.exit(1)

    employee_id = input_data.get("employee_id")
    if not employee_id:
        print(json.dumps({"error": "Missing 'employee_id' in request"}), file=sys.stderr)
        sys.exit(1)

    es_url = "https://172.200.58.63:9200"
    api_key = os.getenv("ELASTICSEARCH_API_KEY")
    cert_path = os.getenv("ELASTICSEARCH_CERT_PATH")

    results = []
    for index_name in ["hrbot", "hrbot_embed"]:
        deleter = ResumeDeleter(es_url, api_key, index_name, cert_path)
        result = deleter.delete_by_employee_id(employee_id)
        results.append(result)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
