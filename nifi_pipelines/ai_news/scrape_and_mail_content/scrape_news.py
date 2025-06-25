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
from pydantic import BaseModel, SecretStr
from browser_use import Agent, BrowserSession, BrowserProfile, Controller
from dotenv import load_dotenv
from asyncio import TimeoutError
from langchain_openai import AzureChatOpenAI
import logging
import time
import signal
import io
from contextlib import contextmanager
import threading
import queue
import traceback
import atexit
import psutil
import functools
import multiprocessing
from typing import List

# Suppress deprecation warnings
import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)

# Configure logging to capture errors
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)

class DetailedErrorHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            if record.exc_info:
                msg += '\n' + ''.join(traceback.format_exception(*record.exc_info))
            sys.stderr.write(msg + '\n')
            sys.stderr.flush()
        except Exception:
            self.handleError(record)

error_handler = DetailedErrorHandler()
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

root_logger = logging.getLogger()
root_logger.addHandler(error_handler)
root_logger.setLevel(logging.ERROR)

logging.getLogger().setLevel(logging.ERROR)
logging.getLogger().handlers = [error_handler]

for logger_name in logging.root.manager.loggerDict:
    logger = logging.getLogger(logger_name)
    logger.handlers = [error_handler]
    logger.propagate = False
    logger.setLevel(logging.ERROR)

logging.getLogger('telemetry').handlers = [error_handler]
logging.getLogger('telemetry').propagate = False
logging.getLogger('browser_use').handlers = [error_handler]
logging.getLogger('browser_use').propagate = False
logging.getLogger('browser_use.telemetry').handlers = [error_handler]
logging.getLogger('browser_use.telemetry').propagate = False
logging.getLogger('browser_use.agent').handlers = [error_handler]
logging.getLogger('browser_use.agent').propagate = False
logging.getLogger('browser_use.agent.service').handlers = [error_handler]
logging.getLogger('browser_use.agent.service').propagate = False
logging.getLogger('posthog').handlers = [error_handler]
logging.getLogger('posthog').propagate = False
logging.getLogger('posthog').disabled = True

load_dotenv()

TIMEOUT_SECONDS = 900.0  # 15 minutes timeout
MAX_RETRIES = 2
RETRY_DELAY = 5  # seconds

AI_NEWS_TASK = """
You are an AI research agent. Your task is to extract the latest developments in AI and generative AI (GenAI) from the following sources:

- https://medium.com/google-cloud
- https://ai.meta.com/blog/
- https://www.ainews.com/
- https://www.reddit.com/r/LocalLLaMA/

Instructions for each source:
1. Navigate to the sources and the news articles or posts inside it which are published within the last 7 days.
2. In total return at least 7 articles or posts, with a maximum of 10 articles or posts from all sources combined.
3. For each relevant item, extract:
   - `title`: The article or post headline.
   - `published_date`: The exact date it was published.
   - `content`: Descriptive and detailed content from the article or post.
   - `source_url`: The direct URL to the article or post.

Constraints:
- Skip any page that fails to load, takes too long, or has inaccessible elements.
- If blocked move to next url, donot attempt to resolve blocks.
- Avoid content that violates Responsible AI policies (e.g., hate speech, misinformation, unethical AI use).
- Do not hallucinate any content. Extract only what is verifiably on the page.

Return your final output strictly in the following JSON format, with no extra text:
{
  "success": true,
  "data": {
    "articles": [
      {
        "title": "string",
        "content": "string",
        "source_url": "string",
        "published_date": "YYYY-MM-DD"
      }
    ]
  }
}
"""

class Article(BaseModel):
    title: str
    content: str
    source_url: str
    published_date: str

class Articles(BaseModel):
    articles: List[Article]

controller = Controller(output_model=Articles)

llm = AzureChatOpenAI(
    model="gpt-4o-mini",
    api_version='2024-12-01-preview',
    azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT', ''),
    api_key=SecretStr(os.getenv('AZURE_OPENAI_KEY', '')),
)

def force_kill_chrome():
    try:
        subprocess.run(['pkill', '-f', 'chrome-linux/chrome'], timeout=5)
        time.sleep(1)
        subprocess.run(['pkill', '-9', '-f', 'chrome-linux/chrome'], timeout=5)
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if any(x in ' '.join(proc.info['cmdline'] or []).lower() for x in ['chrome', 'chromium']):
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except Exception as e:
        logging.error(f"Error during force kill: {str(e)}")

def watchdog_timer():
    time.sleep(TIMEOUT_SECONDS)
    logging.error("Watchdog timer expired - forcing script termination")
    force_kill_chrome()
    os._exit(1)

def timeout_handler(signum, frame):
    logging.error("Script execution exceeded timeout limit")
    force_kill_chrome()
    os._exit(1)

def setup_timeout():
    if sys.platform != 'win32':
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(int(TIMEOUT_SECONDS))
    watchdog = multiprocessing.Process(target=watchdog_timer)
    watchdog.daemon = True
    watchdog.start()

def cleanup_handler(signum, frame):
    logging.error(f"Received signal {signum}, cleaning up...")
    force_kill_chrome()
    os._exit(1)

def setup_cleanup_handlers():
    signals = [signal.SIGTERM, signal.SIGINT]
    if sys.platform != 'win32':
        signals.append(signal.SIGALRM)
    for sig in signals:
        signal.signal(sig, cleanup_handler)

atexit.register(force_kill_chrome)
setup_cleanup_handlers()

def create_browser_session():
    try:
        browser_profile = BrowserProfile(
            headless=True,
            chromium_sandbox=False,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu',
                '--window-size=1920,1080',
                '--disable-extensions',
                '--disable-component-extensions-with-background-pages',
                '--disable-default-apps',
                '--mute-audio',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-background-networking',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-breakpad',
                '--disable-client-side-phishing-detection',
                '--disable-features=TranslateUI',
                '--disable-hang-monitor',
                '--disable-ipc-flooding-protection',
                '--disable-popup-blocking',
                '--disable-prompt-on-repost',
                '--disable-sync',
                '--metrics-recording-only',
                '--safebrowsing-disable-auto-update',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials'
            ],
            viewport={"width": 1920, "height": 1080},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            ignore_https_errors=True,
            java_script_enabled=True,
            accept_downloads=True,
            downloads_dir='/tmp/browser_downloads',
            timeout=30000,
            default_navigation_timeout=30000
        )
        return BrowserSession(browser_profile=browser_profile)
    except Exception as e:
        logging.error(f"Error creating browser session: {str(e)}\n{traceback.format_exc()}")
        raise

async def scrape_ai_news():
    browser_session = None
    for attempt in range(MAX_RETRIES):
        try:
            setup_timeout()
            browser_session = create_browser_session()
            agent = Agent(
                task=AI_NEWS_TASK,
                llm=llm,
                controller=controller,
                enable_memory=True,
                browser_session=browser_session
            )
            try:
                history = await asyncio.wait_for(agent.run(), timeout=TIMEOUT_SECONDS)
                result = history.final_result()
                if result:
                    with open("ai_news.json", "w") as f:
                        f.write(result)
                    return True
                else:
                    if attempt < MAX_RETRIES - 1:
                        logging.error(f"Attempt {attempt + 1} failed: No result returned. Retrying...")
                        await asyncio.sleep(RETRY_DELAY)
                        continue
                    else:
                        error_msg = "No result returned from the agent after all retries"
                        logging.error(error_msg)
                        return False
            except TimeoutError:
                if attempt < MAX_RETRIES - 1:
                    logging.error(f"Attempt {attempt + 1} failed: Timeout. Retrying...")
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                else:
                    error_msg = "Timeout processing AI news after all retries"
                    logging.error(error_msg)
                    return False
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    logging.error(f"Attempt {attempt + 1} failed: {str(e)}. Retrying...")
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                else:
                    error_msg = f"Error processing AI news after all retries: {str(e)}\n{traceback.format_exc()}"
                    logging.error(error_msg)
                    return False
            finally:
                if browser_session:
                    try:
                        await browser_session.close()
                    except Exception as e:
                        logging.error(f"Error closing browser session: {str(e)}")
                force_kill_chrome()
        except Exception as e:
            error_msg = f"Unexpected error in scrape_ai_news: {str(e)}\n{traceback.format_exc()}"
            logging.error(error_msg)
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
                continue
            return False
        finally:
            if sys.platform != 'win32':
                signal.alarm(0)
    return False

async def main_async():
    setup_timeout()
    try:
        success = await asyncio.wait_for(scrape_ai_news(), timeout=TIMEOUT_SECONDS)
        if not success:
            sys.stderr.write("AI news not generated.\n")
            sys.stderr.flush()
            os._exit(1)
    except asyncio.TimeoutError:
        error_msg = "Script execution exceeded 3 minutes"
        logging.error(error_msg)
        force_kill_chrome()
        os._exit(1)
    except Exception as e:
        error_msg = f"Error in main_async: {str(e)}\n{traceback.format_exc()}"
        logging.error(error_msg)
        force_kill_chrome()
        os._exit(1)
    finally:
        if sys.platform != 'win32':
            signal.alarm(0)
        force_kill_chrome()

def main():
    try:
        if sys.platform.startswith('linux'):
            import asyncio
            asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(main_async())
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.stop()
                loop.close()
            except Exception as e:
                logging.error(f"Error during event loop cleanup: {str(e)}")
            finally:
                force_kill_chrome()
    except KeyboardInterrupt:
        logging.error("Script interrupted by user")
        force_kill_chrome()
        os._exit(1)
    except Exception as e:
        logging.error(f"Fatal error: {str(e)}\n{traceback.format_exc()}")
        force_kill_chrome()
        os._exit(1)

if __name__ == '__main__':
    main()
