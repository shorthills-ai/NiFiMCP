#!/usr/bin/env python3

import sys
import json
import traceback
import os
from dotenv import load_dotenv
from elasticsearch import Elasticsearch, NotFoundError
from elasticsearch import exceptions as es_exceptions

load_dotenv()

# Required environment variables
ES_URL = os.getenv("ELASTICSEARCH_URL")
ES_API_KEY = os.getenv("ELASTIC_API_KEY")
ES_CA_CERT = os.getenv("ELASTIC_CA_CERT")

# Fail early if required vars are missing
for var in ["ELASTICSEARCH_URL", "ELASTIC_API_KEY", "ELASTIC_CA_CERT"]:
    if not os.getenv(var):
        sys.stderr.write(f"❌ Missing required environment variable: {var}\n")
        sys.exit(1)


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

    # Delete from hrbot
    deleter_hrbot = ResumeDeleter(ES_URL, ES_API_KEY, "hrbot", ES_CA_CERT)
    result_hrbot = deleter_hrbot.delete_by_employee_id(employee_id)

    # Delete from hrbot_embed (but don't include in output)
    deleter_embed = ResumeDeleter(ES_URL, ES_API_KEY, "hrbot_embed", ES_CA_CERT)
    _ = deleter_embed.delete_by_employee_id(employee_id)

    # Output only result from hrbot
    print(json.dumps(result_hrbot, ensure_ascii=False, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError) as e:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
