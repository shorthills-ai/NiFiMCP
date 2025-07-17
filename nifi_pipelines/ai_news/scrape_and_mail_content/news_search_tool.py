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
from langchain_openai import AzureChatOpenAI
from urllib.parse import urljoin
import re



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
    4.  VERY IMPORTANT: Collect a total of at least 20 unique articles/posts. Distribute your collection across various sources if possible, but prioritize relevance and recentness.
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


### SMOL AI NEWS VARIABLES AND FUNCTIONS
SMOL_AI_BASE_URL = "https://news.smol.ai/"

# --- Configuration for Scraping Logic ---

# 1. Keywords to identify sub-sections to EXCLUDE within the Twitter Recap
TWITTER_SUBSECTIONS_TO_EXCLUDE = [
    "research, evaluation, and ai safety"
    "industry trends, talent & companies"
    "company strategy and the industry landscape",
    "humor, memes, and culture"
]

# 2. Keywords to identify the HARD STOP for all scraping
STOP_SCRAPING_KEYWORDS = [
    "less-technical ai subreddit recap",
    "discord: detailed by-channel summaries and links"
]

# 3. Keywords to identify which Discord channels to INCLUDE
#    The script will match these against the h2 headings in the Discord summary.
DISCORD_CHANNELS_TO_INCLUDE = {
    "perplexity", "openai", "huggingface", "mcp", "llm agents", "llamaindex", "dspy", "nomic.ai"
}


def get_latest_issue_url():
    """Finds the URL for the most recent news issue on the homepage."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(SMOL_AI_BASE_URL, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # The latest issue is usually the first link in the main content area
        main_content = soup.find('main')
        if not main_content:
            return None
            
        latest_issue_link = main_content.find('a', href=re.compile(r'/issues/'))
        if latest_issue_link:
            full_url = urljoin(SMOL_AI_BASE_URL, latest_issue_link['href'])
            return full_url
        else:
            return None
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Error fetching homepage of smol ai newsletter: {e}")

def extract_list_items(ul_element, source_url):
    """Helper function to extract title/content from list items in a <ul>."""
    items = []
    if not ul_element:
        return items
        
    for li in ul_element.find_all('li', recursive=False):
        # The title is usually within a <strong> tag
        strong_tag = li.find('strong')
        if strong_tag:
            title = strong_tag.get_text(strip=True).replace(':', '').strip()
            strong_tag.extract()  # Remove the title part to get the content
            content = li.get_text(strip=True)
            
            if title and content:
                items.append({
                    "title": title,
                    "content": content,
                    "source_url": source_url
                })
    return items

def parse_issue_page(html_content, issue_url):
    """
    Parses the HTML of a specific issue page using a state-machine approach
    to handle complex inclusion/exclusion rules.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    articles = []
    
    article_body = soup.find('article', class_='content-area')
    if not article_body:
        return articles

    current_section = None
    skip_current_subsection = False

    # Iterate through all top-level tags within the article
    for element in article_body.find_all(['h1', 'h2', 'h3', 'p', 'ul'], recursive=False):
        element_text_lower = element.get_text().lower().strip()

        # --- Check for STOP conditions ---
        if any(keyword in element_text_lower for keyword in STOP_SCRAPING_KEYWORDS):
            break
            
        # --- State Management: Determine which section we are in ---
        if element.name == 'h1':
            # Reset subsection skip flag when a new major section starts
            skip_current_subsection = False
            if 'ai twitter recap' in element_text_lower:
                current_section = 'twitter'
            elif 'ai reddit recap' in element_text_lower:
                current_section = 'reddit'
            elif 'discord: high level discord summaries' in element_text_lower:
                current_section = 'discord'
            else:
                current_section = None # We are in a section we don't care about

        # --- Content Processing based on current section state ---
        if current_section == 'twitter':
            # Check for sub-headings to exclude
            if element.name == 'p' and element.find('strong'):
                if any(keyword in element_text_lower for keyword in TWITTER_SUBSECTIONS_TO_EXCLUDE):
                    skip_current_subsection = True
                else:
                    skip_current_subsection = False
            
            # If it's a list and we are not in a skipped subsection, process it
            if element.name == 'ul' and not skip_current_subsection:
                source_url = f"{issue_url}#ai-twitter-recap"
                articles.extend(extract_list_items(element, source_url))

        elif current_section == 'reddit':
            if element.name == 'ul':
                source_url = f"{issue_url}#ai-reddit-recap"
                articles.extend(extract_list_items(element, source_url))

        elif current_section == 'discord':
            # Discord section has a different structure: H2 -> UL for each channel
            if element.name == 'h2':
                channel_name_lower = element.get_text().lower()
                # Check if this is a channel we want to include
                if any(keyword in channel_name_lower for keyword in DISCORD_CHANNELS_TO_INCLUDE):
                    ul_element = element.find_next_sibling('ul')
                    source_url = f"{issue_url}#{element.get('id', 'discord-high-level-discord-summaries')}"
                    articles.extend(extract_list_items(ul_element, source_url))
    
    return articles


### AI NEWS VARIABLES AND FUNCTIONS
AI_NEWS_BASE_URL = "https://www.ainews.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/114.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def fetch_url(session, url, retries=2):
    for i in range(retries):
        r = session.get(url)
        if r.status_code == 403 and i < retries - 1:
            time.sleep(1)
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()

def get_latest_headlines_url(session):
    resp = fetch_url(session, AI_NEWS_BASE_URL)
    soup = BeautifulSoup(resp.text, "html.parser")
    for blk in soup.select("div.w-full.p-3"):
        if blk.find("h2", string=lambda t: t and "Top AiNews.com Headlines" in t):
            a = blk.find("a", href=True)
            return urljoin(AI_NEWS_BASE_URL, a["href"])
    raise RuntimeError("Could not find the Top AiNews.com Headlines link.")

def parse_list_items(ul):
    """Given a <ul>, return list of {title, content, source_url} from its <li>s."""
    out = []
    for li in ul.find_all("li", recursive=False):
        p = li.find("p")
        if not p:
            continue
        a = p.find("a", href=True)
        if not a:
            continue
        title = a.get_text(strip=True)
        href = urljoin(AI_NEWS_BASE_URL, a["href"])
        # remove the link text from the paragraph to get the summary
        full = p.get_text(" ", strip=True)
        content = full.replace(title, "", 1).lstrip(" -–: ")
        out.append({
            "title": title,
            "content": content,
            "source_url": href
        })
    return out

def extract_section(soup, section_id, stop_id=None):
    """
    Extracts all <ul> lists under the <div id=section_id>, stopping when
    it encounters <div id=stop_id> (if provided).
    """
    container = soup.find("div", id=section_id)
    if not container:
        return []

    articles = []
    # iterate siblings until stop_id
    for sib in container.find_next_siblings():
        # stop if we hit the next section
        if stop_id and sib.name == "div" and sib.get("id") == stop_id:
            break
        # find any <ul> within this sib
        for ul in sib.find_all("ul", recursive=False):
            articles.extend(parse_list_items(ul))
    return articles

def create_combined_output():
    """Combines all articles from both json 'shapiroainews.json' and 'smolainews.json' into a single output 'ai_news.json'."""
    combined_output = {"articles": []}
    
    # Load articles from shapiroainews.json
    if os.path.exists("shapiroainews.json"):
        with open("shapiroainews.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            combined_output["articles"].extend(data.get("articles", []))
    
    # Load articles from smolainews.json
    if os.path.exists("smolainews.json"):
        with open("smolainews.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            combined_output["articles"].extend(data.get("articles", []))
    
    # Save the combined output to a new file
    with open("ai_news.json", "w", encoding="utf-8") as f:
        json.dump(combined_output, f, ensure_ascii=False, indent=2)


def main():
    """
    Main function to run for AI news.
    """
    load_dotenv()
    GITHUB_TRENDING_URL = "https://github.com/trending?spoken_language_code=en"
    REPO_OUTPUT_FILE = "trending_repos.json"


    ## smol ai news
    latest_issue_url = get_latest_issue_url()
    
    if latest_issue_url:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(latest_issue_url, headers=headers)
            response.raise_for_status()
            
            articles_list = parse_issue_page(response.text, latest_issue_url)
            
            if articles_list:
                final_output = {"articles": articles_list}
                output_filename = 'smolainews.json'
                with open(output_filename, 'w', encoding='utf-8') as f:
                    json.dump(final_output, f, ensure_ascii=False, indent=2)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to fetch the issue page content from smol ai newsletter: {e}")        

     ## ai news
    session = requests.Session()
    session.headers.update(HEADERS)

    #Fetching homepage
    latest_url = get_latest_headlines_url(session)

    #Downloading article
    resp = fetch_url(session, latest_url)
    soup = BeautifulSoup(resp.text, "html.parser")

    #Extracting Today’s Headlines
    todays = extract_section(soup, section_id="todays-headlines", stop_id="ai-tools")

    #Extracting AI Tools
    # you’ll need to ensure the AI Tools container has id="ai-tools"
    tools = extract_section(soup, section_id="ai-tools", stop_id=None)

    all_articles = todays + tools

    with open("shapiroainews.json", "w", encoding="utf-8") as f:
        json.dump({"articles": all_articles}, f, ensure_ascii=False, indent=2)
    

    time.sleep(10)
    # Create combined output
    create_combined_output()

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

    # search AI news only if ai_news.json has less than 10 articles
    combined_news_path = "ai_news.json"
    run_search_ai_news = True
    if os.path.exists(combined_news_path):
        try:
            with open(combined_news_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                articles = data.get("articles", [])
                if len(articles) >= 10:
                    run_search_ai_news = False
        except Exception:
            pass
    if run_search_ai_news:
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
