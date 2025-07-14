import os
import json
import time
import datetime
import requests
from bs4 import BeautifulSoup
from pydantic import SecretStr
from langchain_openai import AzureChatOpenAI
from dotenv import load_dotenv
from google import genai
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch



def search_ai_news(client,model_id,start_time_str, current_time_str):
    google_search_tool = Tool(
        google_search = GoogleSearch()
    )

    # Configure llm client
    response = client.models.generate_content(
        model=model_id,
        contents="""- https://medium.com/google-cloud
    - https://ai.meta.com/blog/
    - https://www.ainews.com/
    - https://www.reddit.com/r/LocalLLaMA/
    - https://alphasignal.ai/last-email
    - https://www.reddit.com/r/LocalLLM/
    - https://news.smol.ai/
    - https://openai.com/news/""",

        config=GenerateContentConfig(
            tools=[google_search_tool],
            system_instruction=f"""
    You are an AI research agent. Your primary task is to meticulously extract diverse and recent developments in Artificial Intelligence (AI), Generative AI (GenAI), Large Language Models (LLMs), AI tools, and MCP server related news.

    Focus on:
    - AI advancements and breakthroughs
    - GenAI tools and platforms
    - Tools and platforms for building AI applications
    - New LLM releases and research
    - MCP server updates using LLMs
    - Advances in multimodal AI, embeddings, chunking, MCP servers, internet/deep search, agent-to-agent protocols, and no-code/low-code AI pipelines

    Instructions:
    1.  You have been provided with some initial website URLs. While these are a starting point, do not limit your search space to these websites only.
    2.  You are free to search the entire Google index, including news sites, blogs, research papers, and social media platforms like Twitter.
    3.  If you find relevant news on Twitter, include it. If a Twitter post contains a URL to a more detailed article, prioritize the article's URL.
    4.  VERY IMPORTANT: Collect a total of at least 40 unique articles/posts. Distribute your collection across various sources if possible, but prioritize relevance and recentness.
    5.  Date Constraint: Only extract articles, posts, or news items published **within the last 24 hours**. Your search window is strictly from **{start_time_str}** to **{current_time_str}**.
    6. Content Extraction per Item: For each relevant item, extract:
        *   `title`: The exact headline of the article or post.
        *   `published_date`: The precise publication date in "YYYY-MM-DD" format. If an exact day isn't available but the month/year indicates it's within the last week (e.g., "June 2025" for a scrape run in late June 2025), use the first day of that period or the most accurate date you can infer that falls within the last 7 days. If a clear date within the timeframe cannot be established, skip the item.
        *   `content`: A descriptive and detailed summary of the key information, developments, insights, or announcements from the article or post. Capture the essence and important details that make it newsworthy in the context of AI advancements.
        *  `summary`: A 2-3 line short summary of the article or post capturing the main points or findings.
        *   `source_url`: The direct permalink to the article or post.

    Return your final output strictly in the following format, with no extra text:
    {{
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


def scrape_github_trending(github_url):
    """
    Scrapes the GitHub trending page for English language repositories.

    Returns:
        list: A list of dictionaries, where each dictionary contains the
              name, URL, and description of a repository. Returns an empty
              list if scraping fails.
    """
    try:
        response = requests.get(github_url, timeout=15)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
    except requests.exceptions.RequestException as e:
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    repo_list = []
    
    # Each trending repository is an <article> with class 'Box-row'
    repo_articles = soup.find_all('article', class_='Box-row')

    for article in repo_articles:
        # Extract repository name and URL
        h2_tag = article.find('h2', class_='h3')
        if not h2_tag:
            continue
        
        a_tag = h2_tag.find('a', href=True)
        if not a_tag:
            continue
            
        repo_name = a_tag.get_text(strip=True).replace(" / ", "/")
        repo_url = "https://github.com" + a_tag['href']

        # Extract description
        p_tag = article.find('p', class_='col-9')
        description = p_tag.get_text(strip=True) if p_tag else "No description provided."

        repo_list.append({
            "repo_name": repo_name,
            "repo_url": repo_url,
            "description": description
        })
        
    return repo_list

def filter_repos_with_ai(llm,repos_to_filter: list):
    """
    Uses a generative AI model to filter repositories based on relevance to
    AI-related topics.

    Args:
        repos_to_filter (list): A list of repository dictionaries.

    Returns:
        list: A new list containing only the repositories deemed relevant by the AI.
    """

    filtered_repos = []
    
    # This is the prompt that will instruct the AI
    system_prompt = """
    You are an expert AI software engineer. Your task is to determine if a GitHub repository is related to any of the following topics:
    - Generative AI
    - MCP (Model-Context-Protocol)
    - RAG (Retrieval-Augmented Generation)
    - LLM (Large Language Model)
    - General AI (Artificial Intelligence) tools, libraries, or applications.
    - Vector databases or vector search engines.

    I will provide you with the repository name and its description.
    You must respond with only 'YES' or 'NO'. Do not add any explanation or punctuation.
    """

    for i, repo in enumerate(repos_to_filter):
        repo_info = f"Repository Name: {repo['repo_name']}\nDescription: {repo['description']}"
        
        try:
            # The full prompt combines the system instruction and the specific repo info
            full_prompt = f"{system_prompt}\n\n{repo_info}"
            response = llm.invoke(full_prompt)
            
            answer = response.content.strip().upper()
            
            if answer == "YES":
                filtered_repos.append(repo)

            # Add a small delay to respect API rate limits
            time.sleep(2)

        except Exception as e:
            # Continue to the next repo even if one fails
            continue

    return filtered_repos

def save_to_json(data: list, filename: str):
    """
    Saves the provided data to a JSON file in the specified format.

    Args:
        data (list): The list of repositories to save.
        filename (str): The name of the output JSON file.
    """
    output_structure = {
            "repos": data
        }

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output_structure, f, indent=2, ensure_ascii=False)
    except IOError as e:
        raise IOError(f"Error writing to file {filename}: {e}")


def main():
    """
    Main function to run for AI news.
    """
    load_dotenv()
    GITHUB_TRENDING_URL = "https://github.com/trending?spoken_language_code=en"
    REPO_OUTPUT_FILE = "trending_repos.json"

    # Initialize Azure OpenAI model instance
    llm = AzureChatOpenAI(
            model="gpt-4o-mini",
            api_version='2024-12-01-preview',
            azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT', ''),
            api_key=SecretStr(os.getenv('AZURE_OPENAI_KEY', '')),
            )

    google_api_key = os.getenv("GOOGLE_API_KEY")
    model_id = "gemini-2.5-pro-preview-03-25"
    client = genai.Client()

    # current_date = datetime.date.today().strftime("%Y-%m-%d")
    current_utc_time = datetime.datetime.now(datetime.timezone.utc)

    start_utc_time = current_utc_time - datetime.timedelta(hours=24)

    #format time to string
    current_time_str = current_utc_time.strftime("%Y-%m-%d %H:%M:%S %Z")
    start_time_str = start_utc_time.strftime("%Y-%m-%d %H:%M:%S %Z")

    # search AI news
    search_ai_news(client,model_id,start_time_str, current_time_str)

    # scrape GitHub trending repositories
    scraped_repos = scrape_github_trending(github_url=GITHUB_TRENDING_URL)
    
    if not scraped_repos:
        # Still create an empty file
        save_to_json([], REPO_OUTPUT_FILE)
        return
        
    relevant_repos = filter_repos_with_ai(llm,scraped_repos)
    save_to_json(relevant_repos, REPO_OUTPUT_FILE)


if __name__ == "__main__":
    main()
