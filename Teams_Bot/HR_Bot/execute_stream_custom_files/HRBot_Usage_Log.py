#!/usr/bin/env python3

import sys
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path="/home/nifi/nifi2/HR_Bot/.env")

# Read log line from stdin
log_line = sys.stdin.read().strip()

# Log file path from env with fallback
log_file_path = os.getenv('LLM_USAGE_LOG_PATH', '/home/nifi/nifi2/HR_Bot/llm_usage.log')

# Append the log line to the file
with open(log_file_path, 'a') as f:
    f.write(log_line + '\n')
