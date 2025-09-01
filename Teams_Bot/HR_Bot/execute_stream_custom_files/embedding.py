import sys
import json
import openai
from openai import AzureOpenAI
 
from elasticsearch import Elasticsearch
import urllib3
 
# Disable SSL warnings for dev environments
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
cert_path="CERT_PATH"
 
# Elasticsearch Configuration
es = Elasticsearch(
    "https://172.200.58.63:9200",
    api_key="ES_API_KEY",
    verify_certs=True,
    ca_certs=cert_path
)
index_name = "hrbot_embed"
 
 
client = AzureOpenAI(
    api_key="AZURE_OPENAI_API_KEY",
    api_version="AZURE_OPENAI_API_VERSION",
    azure_endpoint="AZURE_OPENAI_ENDPOINT"
)
 
def get_embedding(text):
    if not text.strip():
        return None
    try:
        response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"❌ Azure embedding error: {e}", file=sys.stderr)
        return None
 
def main():
    try:
        data = json.load(sys.stdin)
    except Exception as e:
        print(f"❌ Failed to read JSON from stdin: {e}", file=sys.stderr)
        sys.exit(1)
 
    employee_id = data.get("employee_id")
    if not employee_id:
        print("⚠️ Missing employee_id.", file=sys.stderr)
        sys.exit(1)
 
    parts = []
 
    if summary := data.get("summary"):
        parts.append("Summary: " + summary)
 
    if isinstance(data.get("skills"), list):
        parts.append("Skills: " + ", ".join(data["skills"]))
 
    if isinstance(data.get("education"), list):
        edu_lines = [f"{e.get('degree', '')} - {e.get('institution', '')} ({e.get('year', '')})" for e in data["education"]]
        parts.append("Education:\n" + "\n".join(edu_lines))
 
    if isinstance(data.get("experience"), list):
        exp_lines = [
            f"{e.get('title', '')} at {e.get('company', '')}, {e.get('location', '')} ({e.get('duration', '')})"
            for e in data["experience"]
        ]
        parts.append("Experience:\n" + "\n".join(exp_lines))
 
    if isinstance(data.get("projects"), list):
        proj_lines = [
            f"{p.get('title', '')}: {p.get('description', '')}"
            for p in data["projects"]
        ]
        parts.append("Projects:\n" + "\n\n".join(proj_lines))
 
    if isinstance(data.get("certifications"), list) and data["certifications"]:
        cert_lines = []
        for cert in data["certifications"]:
            if isinstance(cert, dict):
                cert_lines.append(", ".join(f"{k}: {v}" for k, v in cert.items()))
            else:
                cert_lines.append(str(cert))
        parts.append("Certifications:\n" + "\n".join(cert_lines))
 
    embedding_input = "\n\n".join(parts).strip()
    if not embedding_input:
        print("⚠️ No relevant fields found.", file=sys.stderr)
        sys.exit(1)
 
    embedding = get_embedding(embedding_input)
    if not embedding or sum(embedding) == 0.0:
        print("⚠️ Invalid embedding.", file=sys.stderr)
        sys.exit(1)
 
    try:
        es.index(index=index_name, id=employee_id, document={
            "content": embedding_input,
            "vector": embedding,
            "metadata": {
                "name": data.get("name"),
                "certifications": data.get("certifications", []),
                "links": data.get("links", [])
            }
        })
        print(f"✅ Indexed employee_id: {employee_id}")
    except Exception as e:
        print(f"❌ Error indexing document: {e}", file=sys.stderr)
        sys.exit(1)
 
if __name__ == "__main__":
    main()