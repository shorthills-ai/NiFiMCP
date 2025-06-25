import os
import json
import datetime
from dotenv import load_dotenv
from google import genai
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch

load_dotenv()

google_api_key = os.getenv("GOOGLE_API_KEY")

client = genai.Client()
model_id = "gemini-2.5-pro-preview-03-25"

google_search_tool = Tool(
    google_search = GoogleSearch()
)

current_date = datetime.date.today().strftime("%Y-%m-%d")

response = client.models.generate_content(
    model=model_id,
    contents="""- https://medium.com/google-cloud
- https://ai.meta.com/blog/
- https://www.ainews.com/
- https://www.reddit.com/r/LocalLLaMA/""",

    config=GenerateContentConfig(
        tools=[google_search_tool],
        system_instruction=f"""
You are an AI research agent. Your primary task is to meticulously extract diverse and recent developments in Artificial Intelligence (AI), Generative AI (GenAI), Large Language Models (LLMs), AI tools, AI's societal/industrial impact, and MCP server related news.

Focus on:
- AI advancements and breakthroughs
- GenAI tools and platforms
- Software industry impact of AI
- New LLM releases and research
- MCP server updates using LLMs
- Advances in multimodal AI, embeddings, chunking, MCP servers, internet/deep search, agent-to-agent protocols, and no-code/low-code AI pipelines

Instructions:
1.  You have been provided with some initial website URLs. While these are a starting point, do not limit your search space to these websites only.
2.  You are free to search the entire Google index, including news sites, blogs, research papers, and social media platforms like Twitter.
3.  If you find relevant news on Twitter, include it. If a Twitter post contains a URL to a more detailed article, prioritize the article's URL.
4.  VERY IMPORTANT: Collect a total of at least 20 unique articles/posts. Distribute your collection across various sources if possible, but prioritize relevance and recentness.
5.  Date Constraint: Only extract articles, posts, or news items published **within the last 7 days from the current date: {current_date}**.
6. Content Extraction per Item: For each relevant item, extract:
    *   `title`: The exact headline of the article or post.
    *   `published_date`: The precise publication date in "YYYY-MM-DD" format. If an exact day isn't available but the month/year indicates it's within the last week (e.g., "June 2025" for a scrape run in late June 2025), use the first day of that period or the most accurate date you can infer that falls within the last 7 days. If a clear date within the timeframe cannot be established, skip the item.
    *   `content`: A descriptive and detailed summary of the key information, developments, insights, or announcements from the article or post. Capture the essence and important details that make it newsworthy in the context of AI advancements.
    *  `summary`: A 2-3 line short summary of the article or post capturing the main points or findings.
    *   `source_url`: The direct permalink to the article or post.

Return your final output strictly in the following format, with no extra text:
{{
  "success": true,
  "data": {{
    "articles": [
      {{
        "title": "string",
        "content": "string",
        "summary": "string",
        "source_url": "string",
        "published_date": "YYYY-MM-DD"
      }}
    ]
  }}
}}
        """,
        response_modalities=["TEXT"],
    )
)

output_file_path = "ai_news.json"

full_response_text = ""
if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
    for part in response.candidates[0].content.parts:
        full_response_text += part.text

if full_response_text:
    clean_response_text = full_response_text.replace("```json", "").replace("```", "").strip()
    try:
        news_data = json.loads(clean_response_text)
        with open(output_file_path, 'w') as f:
            json.dump(news_data["data"], f, indent=2)
    except json.JSONDecodeError:
        raise ValueError("google search tool: Failed to decode JSON from the response content.")
else:
    raise ValueError("google search tool: No content parts found in the response candidates.")
