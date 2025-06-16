import asyncio
import os
import json
import sys
import logging
import warnings
# from dotenv import load_dotenv
from utils import LLMProvider
from browser_use import Agent, Controller
from pydantic import BaseModel
from typing import List
from pydantic import SecretStr


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

# load_dotenv()

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
    author: str

class Articles(BaseModel):
    articles: List[Article]

controller = Controller(output_model=Articles)

task = """
Research the latest developments regarding AI, Generative AI, agentic AI and related tools from at least 3 different reputable sources.

For each source:
1. Navigate to their search function and find articles about the AI from the past week.
2. Extract the headline, publication date, and author.
3. Extract the main content of the article, ensuring it is informative.
4. Add the source url to the article.
5. Do not include anything that may violate ResponsibleAIPolicy.

If a page fails to load, takes too long, or an element is not clickable, skip to the next source.

After gathering information, return the result in JSON format with the following structure:
{
  "success": true,
  "data": {
    "articles": [
      {
        "title": "article title",
        "content": "article content",
        "source_url": "source url",
        "published_date": "publication date",
        "author": "author name"
      }
    ]
  }
}
Return ONLY the final result as a JSON object matching this format, and nothing else.
"""

async def main():
    agent = Agent(
        task=task,
        llm=llm,
        controller=controller,
        # tool_calling_method='raw',
        enable_memory=True,
    )
    history = await agent.run()
    result = history.final_result()
    if result:
        with open(f"ai_news.json", "w") as f:
            f.write(result)
        # Parse the wrapped result
        try:
            result_json = json.loads(result)
            articles_data = result_json["data"]
            parsed = Articles.model_validate(articles_data)
        except Exception:
            sys.exit(1)
        with open("ai_news_results_pretty.json", "w") as f:
            json.dump(parsed.model_dump(), f, indent=2, ensure_ascii=False)
        # Print the pretty JSON to stdout
        print(json.dumps(parsed.model_dump(), indent=2, ensure_ascii=False))
        return  # Success, exit with code 0
    else:
        sys.exit(1)

asyncio.run(main())
