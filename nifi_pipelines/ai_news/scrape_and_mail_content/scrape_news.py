import asyncio
import os
import json
import sys
import logging
import warnings
#from dotenv import load_dotenv
#load_dotenv()
from browser_use import BrowserSession, Agent, Controller
from langchain_openai import AzureChatOpenAI
from pydantic import BaseModel
from typing import List
from pydantic import SecretStr
from pathlib import Path
import uuid

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.CRITICAL)
for logger_name in logging.root.manager.loggerDict:
    logging.getLogger(logger_name).setLevel(logging.CRITICAL)
try:
    import playwright
    logging.getLogger("playwright").setLevel(logging.CRITICAL)
except ImportError:
    pass
logging.getLogger("browser_use").setLevel(logging.CRITICAL)



llm = AzureChatOpenAI(
        model="gpt-4o-mini",
        api_version='2024-12-01-preview',
        azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT', ''),
        api_key=SecretStr(os.getenv('AZURE_OPENAI_KEY', '')),
        )

class Article(BaseModel):
    title: str
    content: str
    source_url: str
    published_date: str

class Articles(BaseModel):
    articles: List[Article]

controller = Controller(output_model=Articles)

task = """
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



async def main():
    browser_session = BrowserSession(
        headless=True,
        chromium_sandbox=False,
        viewport={'width': 964, 'height': 647},
        keep_alive=True,
        user_data_dir='~/.config/browseruse/profiles/default',
    )

    try:
        await browser_session.start()

        agent = Agent(
            task=task,
            llm=llm,
            controller=controller,
            enable_memory=True,
            browser_session=browser_session
        )

        history = await agent.run()
        result = history.final_result()

        if result:
            with open("ai_news.json", "w") as f:
                f.write(result)
        else:
            raise Exception("No result returned from the agent.")

    finally:
        # This ensures browser session is always closed, even if there's an error
        await browser_session.kill()

asyncio.run(main())
