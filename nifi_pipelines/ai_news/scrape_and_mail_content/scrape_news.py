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


prompt = """
You are an AI research agent. Your primary task is to meticulously extract diverse and recent developments in Artificial Intelligence (AI), Generative AI (GenAI), Large Language Models (LLMs), AI tools, AI's societal/industrial impact, and MCP server related news from the specified sources.

Sources to scrape:
- https://medium.com/google-cloud
- https://ai.meta.com/blog/
- https://www.ainews.com/
- https://www.reddit.com/r/LocalLLaMA/ (focus on posts announcing new models, tools, significant findings, or discussions around major AI news)
- https://alphasignal.ai/last-email (if this is a newsletter, extract distinct news items or articles linked/summarized within)
- https://www.deeplearning.ai/the-batch/
- https://www.deeplearning.ai/the-batch/tag/letters/

VERY IMPORTANT: Collect a total of at least 15 unique articles/posts, with a maximum of 25, from all sources combined. Distribute your collection across the sources if possible, but prioritize relevance and recentness.

Instructions for extraction:
1.  Date Constraint: Only extract articles, posts, or news items published **within the last 7 days from the current date**.
2.  Variety and Scope: Ensure a diverse range of topics. Prioritize news related to:
    *   New AI model releases or significant updates (e.g., new LLMs, image/video generation models, open-source models).
    *   Developments in AI tools and software (e.g., new libraries, development environments, AI-powered applications, software around generative AI).
    *   News related to AI infrastructure, including MCP server (Model Context Protocol) developments or similar technologies enabling AI model interaction with data/tools.
    *   The societal and industrial impact of AI (e.g., legal rulings like fair use, ethical discussions, major industry adoption news, copyright issues).
    *   Significant research breakthroughs, new company initiatives in AI/GenAI, or updates on existing large language models.
3.  Content Extraction per Item: For each relevant item, extract:
    *   `title`: The exact headline of the article or post.
    *   `published_date`: The precise publication date in "YYYY-MM-DD" format. If an exact day isn't available but the month/year indicates it's within the last week (e.g., "June 2025" for a scrape run in late June 2025), use the first day of that period or the most accurate date you can infer that falls within the last 7 days. If a clear date within the timeframe cannot be established, skip the item.
    *   `content`: A descriptive and detailed summary of the key information, developments, insights, or announcements from the article or post. Capture the essence and important details that make it newsworthy in the context of AI advancements.
    *   `source_url`: The direct permalink to the article or post.

Constraints:
-   If a page or source fails to load, takes an excessive amount of time, or presents inaccessible elements, skip it and move to the next.
-   Strictly avoid content that infringes on Responsible AI guidelines (e.g., hate speech, misinformation, harmful content, unethical AI applications).
-   Do not invent or hallucinate any information. All extracted data must be verifiably present on the source page.
-   If a source like a Reddit thread or newsletter links to external original articles for its news items, prefer extracting information from those original articles if directly accessible and it meets the date criteria. If not, summarize from the provided source.

Return your final output **strictly** in the following JSON format, with no introductory or concluding text outside the JSON structure:
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

smart_scraper_graph = SearchGraph(
    prompt=prompt,
    config=graph_config,
)

try:
    result = smart_scraper_graph.run()

    if result and isinstance(result, dict) and result.get("data") and isinstance(result["data"].get("articles"), list):
        articles_data = result.get("data")
        output_filename = "ai_news.json"
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(articles_data, f, indent=2, ensure_ascii=False)
    else:
        sys.exit(1)

except Exception as e:
    sys.exit(1)
