import sys
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv( )

try:
    # Read JSON input from stdin
    data = json.load(sys.stdin)

    # Extract fields with default fallbacks
    model = data.get("llm_model", "UNKNOWN")
    task_type = data.get("llm_task_type", "Resume Standardisation")  # Optional custom type
    prompt = data.get("llm_prompt_tokens", 0)
    completion = data.get("llm_completion_tokens", 0)
    cost = data.get("llm_total_cost", "$0")

    # Format timestamp and log line
    timestamp = datetime.now().isoformat()
    log_line = (
        f"LLM_USAGE | {timestamp} | "
        f"model={model} | type={task_type} | "
        f"prompt_tokens={prompt} | completion_tokens={completion} | total_cost={cost}"
    )

    # Append to usage log
    log_path = os.getenv("LLM_USAGE_LOG_PATH", "/home/nifi/nifi2/HR_Bot/llm_usage.log")
    with open(log_path, "a") as f:
        f.write(log_line + "\n")

except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
