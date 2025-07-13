import sys
import json
from datetime import datetime, timedelta, timezone
from elasticsearch import Elasticsearch, helpers

try:
    # Read NiFi input from stdin
    input_data = sys.stdin.read()
    if not input_data.strip():
        print("No input data received from NiFi.", file=sys.stderr)
        sys.exit(1)

    # Parse JSON input
    data = json.loads(input_data)

    # Define IST timezone (UTC+5:30)
    IST = timezone(timedelta(hours=5, minutes=30))
    current_time = datetime.now(IST).isoformat()

    # Prepare Elasticsearch client
    client = Elasticsearch(
        "https://172.200.58.63:9200",
        api_key="bDhLS3haY0J5emY3NTkxU0s5ekQ6OW4tTkduaUpHb0VFQkhPLVh3blV1dw==",
        verify_certs=False
    )

    # Prepare docs for bulk insert
    docs = [{
        "_index": "hrbot1",
        "_source": {
            "filename": data.get("filename", "unknown"),
            "text": data.get("text", ""),
            "embedding": data.get("embedding", [0.001] * 768),
            "timestamp": current_time
        }
    }]

    # Execute bulk insert
    bulk_response = helpers.bulk(client, docs)
    print("Bulk insert successful:", bulk_response)

except json.JSONDecodeError as e:
    print(f"JSON decode error: {str(e)}", file=sys.stderr)
    sys.exit(1)

except Exception as e:
    print(f"Unexpected error: {str(e)}", file=sys.stderr)
    sys.exit(1)
