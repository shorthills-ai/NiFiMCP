from langchain_openai import AzureChatOpenAI
import json
import os
import sys
from pydantic import SecretStr
from dotenv import load_dotenv
load_dotenv()

llm_model_instance = AzureChatOpenAI(
        model="gpt-4o-mini",
        api_version='2024-12-01-preview',
        azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT', ''),
        api_key=SecretStr(os.getenv('AZURE_OPENAI_KEY', '')),
        )

graph_config = {
    "llm": {
        "model_instance": llm_model_instance,
        "model_tokens": 128000 
    },
   "verbose": False,
   "headless": True,
}

from scrapegraphai.graphs import SearchGraph

smart_scraper_graph = SearchGraph(
    prompt = """
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
""",
    config=graph_config,
)

result = smart_scraper_graph.run()
articles = result["data"]
if result:
    with open("ai_news.json", "w") as f:
        json.dump(articles, f, indent=2)
else:
    sys.exit(1)
