# Set environment variables before any imports
import os
os.environ['BROWSER_USE_DISABLE_TELEMETRY'] = '1'
os.environ['BROWSER_USE_TELEMETRY_ENABLED'] = '0'
os.environ['ANONYMIZED_TELEMETRY'] = 'false'
os.environ['BROWSER_USE_LOGGING_LEVEL'] = 'error'

import asyncio
import json
import re
import subprocess
import sys
import argparse
from pydantic import BaseModel
from browser_use import Agent
from dotenv import load_dotenv
from asyncio import TimeoutError
from langchain_openai import AzureChatOpenAI
from pydantic import SecretStr
import logging
import time
import signal
import sys
import io
from contextlib import contextmanager
import threading
import queue
import logging.handlers

# Configure logging before any other imports
logging.basicConfig(level=logging.ERROR)
for logger_name in logging.root.manager.loggerDict:
    logging.getLogger(logger_name).setLevel(logging.ERROR)

# Create and set up a null handler
class NullHandler(logging.Handler):
    def emit(self, record):
        pass

null_handler = NullHandler()
null_handler.setLevel(logging.ERROR)

# Disable all logging
logging.getLogger().setLevel(logging.ERROR)
logging.getLogger().handlers = [null_handler]

# Disable all existing loggers
for logger_name in logging.root.manager.loggerDict:
    logger = logging.getLogger(logger_name)
    logger.handlers = [null_handler]
    logger.propagate = False
    logger.setLevel(logging.ERROR)

# Specifically disable browser_use telemetry logging
logging.getLogger('telemetry').handlers = [null_handler]
logging.getLogger('telemetry').propagate = False
logging.getLogger('browser_use').handlers = [null_handler]
logging.getLogger('browser_use').propagate = False
logging.getLogger('browser_use.telemetry').handlers = [null_handler]
logging.getLogger('browser_use.telemetry').propagate = False
logging.getLogger('browser_use.agent').handlers = [null_handler]
logging.getLogger('browser_use.agent').propagate = False
logging.getLogger('browser_use.agent.service').handlers = [null_handler]
logging.getLogger('browser_use.agent.service').propagate = False
logging.getLogger('posthog').handlers = [null_handler]
logging.getLogger('posthog').propagate = False
logging.getLogger('posthog').disabled = True

# Load environment variables
load_dotenv()

# Constants
TIMEOUT_SECONDS = 120.0  # 2 minutes timeout

class OutputCapture:
    def __init__(self):
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        self._stdout_queue = queue.Queue()
        self._stderr_queue = queue.Queue()
        self._stdout_thread = None
        self._stderr_thread = None
        self._captured_stdout = []
        self._captured_stderr = []
        self._original_log_levels = {}
        self._original_handlers = {}

    def _stdout_worker(self):
        while True:
            try:
                line = self._stdout_queue.get()
                if line is None:
                    break
                # Filter out telemetry messages and any logging output
                if not any(x in line for x in ['INFO', 'DEBUG', 'WARNING', 'ERROR', 'CRITICAL', '[telemetry]', 'telemetry']):
                    self._captured_stdout.append(line)
            except queue.Empty:
                break

    def _stderr_worker(self):
        while True:
            try:
                line = self._stderr_queue.get()
                if line is None:
                    break
                # Filter out telemetry messages and any logging output
                if not any(x in line for x in ['INFO', 'DEBUG', 'WARNING', 'ERROR', 'CRITICAL', '[telemetry]', 'telemetry']):
                    self._captured_stderr.append(line)
            except queue.Empty:
                break

    def __enter__(self):
        # Store original log levels and handlers
        for logger_name in logging.root.manager.loggerDict:
            logger = logging.getLogger(logger_name)
            self._original_log_levels[logger_name] = logger.level
            self._original_handlers[logger_name] = logger.handlers
            logger.handlers = [null_handler]
            logger.propagate = False
            logger.setLevel(logging.ERROR)

        # Create a pipe for stdout
        self._stdout_pipe_r, self._stdout_pipe_w = os.pipe()
        self._stderr_pipe_r, self._stderr_pipe_w = os.pipe()
        
        # Start worker threads
        self._stdout_thread = threading.Thread(target=self._stdout_worker)
        self._stderr_thread = threading.Thread(target=self._stderr_worker)
        self._stdout_thread.start()
        self._stderr_thread.start()
        
        # Redirect stdout and stderr
        sys.stdout = os.fdopen(self._stdout_pipe_w, 'w')
        sys.stderr = os.fdopen(self._stderr_pipe_w, 'w')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Close the write ends of the pipes
        sys.stdout.close()
        sys.stderr.close()
        
        # Send None to stop the worker threads
        self._stdout_queue.put(None)
        self._stderr_queue.put(None)
        
        # Wait for threads to finish
        self._stdout_thread.join()
        self._stderr_thread.join()
        
        # Restore original stdout and stderr
        sys.stdout = self._stdout
        sys.stderr = self._stderr

        # Restore original log levels and handlers
        for logger_name in self._original_log_levels:
            logger = logging.getLogger(logger_name)
            logger.handlers = self._original_handlers[logger_name]
            logger.setLevel(self._original_log_levels[logger_name])

def signal_handler(signum, frame):
    print("⏱️ Script execution exceeded 2 minutes", file=sys.stderr)
    sys.exit(1)

def install_dependencies():
    """Install system dependencies for headless browser on Linux."""
    if not sys.platform.startswith('linux'):
        return

    try:
        print("Installing system dependencies for headless browser...", file=sys.stderr)
        subprocess.run(['sudo', 'apt-get', 'update'], check=True)
        subprocess.run(['sudo', 'apt-get', 'install', '-y', 
                      'libnss3', 'libnspr4', 'libatk1.0-0', 'libatk-bridge2.0-0', 'libcups2',
                      'libdrm2', 'libxkbcommon0', 'libxcomposite1', 'libxdamage1', 'libxfixes3',
                      'libxrandr2', 'libgbm1', 'libasound2', 'libpango-1.0-0', 'libcairo2'], check=True)
        subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'], check=True)
        subprocess.run([sys.executable, '-m', 'playwright', 'install-deps'], check=True)
        print("✅ Dependencies installed successfully.", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error installing dependencies: {e}", file=sys.stderr)
        sys.exit(1)

class UsedResult(BaseModel):
    data: dict

# Initialize LLM
llm = AzureChatOpenAI(
    model="gpt-4o-mini",
    api_version='2024-12-01-preview',
    azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT', ''),
    api_key=SecretStr(os.getenv('AZURE_OPENAI_KEY', '')),
)

async def scrape_url(url: str) -> str:
    """Scrape a single URL and return the JSON result."""
    prompt = f"""You are given the website URL: {url}
This page consists of details about an automobile or related product's part. Find the section with product details like description or specifications. If the URL ends with '.pdf', skip it.
Your final output should be a JSON object with:
- data: JSON object containing part details.
IMPORTANT: Return ONLY the raw JSON. No comments, labels, or markdown.
"""

    # Configure agent with correct tool calling method
    agent = Agent(
        task=prompt, 
        llm=llm,
        tool_calling_method='function_calling'
    )

    # Disable telemetry after agent creation
    if hasattr(agent, 'telemetry'):
        agent.telemetry = None

    try:
        # Use OutputCapture to suppress all output during agent.run()
        with OutputCapture():
            history = await asyncio.wait_for(agent.run(), timeout=TIMEOUT_SECONDS)
    except TimeoutError:
        print(f"⏱️ Timeout processing URL: {url}", file=sys.stderr)
        return json.dumps({"error": "Timeout processing URL"})
    except Exception as e:
        print(f"❌ Error processing URL: {e}", file=sys.stderr)
        return json.dumps({"error": str(e)})

    extracted_contents = history.extracted_content()
    result_json = extracted_contents[-2] if len(extracted_contents) >= 2 else None

    if not result_json:
        return json.dumps({"error": "No content extracted"})

    try:
        # Remove unnecessary text, formatting, or code blocks
        cleaned_json = re.sub(r'📄\s+Extracted from page\s*:?\s*', '', result_json)
        cleaned_json = re.sub(r'```json|```', '', cleaned_json).strip()
        
        # Parse and re-serialize to ensure clean JSON
        parsed_json = json.loads(cleaned_json)
        return json.dumps(parsed_json)
    except Exception as parse_err:
        return json.dumps({"error": f"Error parsing result: {str(parse_err)}"})

async def main_async():
    parser = argparse.ArgumentParser(description='Scrape product details from a URL')
    parser.add_argument('url', help='URL to scrape')
    args = parser.parse_args()

    # Install dependencies if needed
    install_dependencies()

    # Set up signal handler for timeout
    signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(int(TIMEOUT_SECONDS))

    try:
        # Run the scraping with timeout
        result = await asyncio.wait_for(scrape_url(args.url), timeout=TIMEOUT_SECONDS)
        
        # Output only the clean JSON to stdout
        sys.stdout.write(result)
        sys.stdout.flush()
        
    except asyncio.TimeoutError:
        print("⏱️ Script execution exceeded 2 minutes", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
    finally:
        # Disable the alarm
        signal.alarm(0)

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n⚠️ Script interrupted by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Fatal error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
