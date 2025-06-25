import json

data = {
    "filename": "example.pdf",
    "text": "This document explains how to configure Elasticsearch.",
    "embedding": [0.001] * 1536
}

with open("valid_payload.json", "w") as f:
    json.dump(data, f)
