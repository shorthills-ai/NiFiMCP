from elasticsearch import Elasticsearch

client = Elasticsearch(
        "https://22f11ab875944bd2982501e7639c5c0f.us-central1.gcp.cloud.es.io:443",
        api_key="d1RPa2dwY0J5Y09JTFFVaDJhaU06WlpDbW91a21PWFZxcTdfYWxOUksydw=="
    )


index_name = "hrbot"

mappings = {
    "properties": {
        "filename": {
            "type": "keyword"
        },
        "text": {
            "type": "text"
        },
        "embedding": {
            "type": "dense_vector",
            "dims": 1536
        },
        "timestamp": {
            "type": "date"
        }
    }
}

# Apply the mapping (make sure index exists before doing this)
mapping_response = client.indices.put_mapping(index=index_name, body=mappings)
print(mapping_response)
