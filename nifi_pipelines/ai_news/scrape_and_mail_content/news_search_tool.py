import os
from urllib.parse import urlparse
from transformers import pipeline
import json
import feedparser
import time
#import requests
from urllib.parse import quote
from bs4 import BeautifulSoup
# from pydantic import SecretStr  # No longer needed for OpenAI
from dotenv import load_dotenv
from google import genai
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch
from urllib.parse import urljoin
import re
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from curl_cffi import requests
total_cost = 0
input_tokens = 0
output_tokens = 0
# Initialize the sentence transformer model globally to avoid reloading
_embedding_model = None

def get_embedding_model():
    """Get or initialize the sentence transformer model."""
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer('Qwen/Qwen3-Embedding-0.6B')
    return _embedding_model

def load_cache():
    """Load the news cache from file."""
    cache_file = "news_cache.json"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                filedata= json.load(f)
                for article in filedata["articles"]:
                    if '_embedding' in article:
                        article['_embedding'] = np.array(article['_embedding'])
                return filedata
        except (json.JSONDecodeError, FileNotFoundError):
            return {"articles": []}
    return {"articles": []}

def save_cache(cache_data):
    """Save the news cache to file."""
    cache_file = "news_cache.json"
    for article in cache_data["articles"]:
        article["timestamp"] = datetime.now(timezone.utc).isoformat()
        if '_embedding' in article:
            article['_embedding'] = article['_embedding'].tolist() if isinstance(article['_embedding'], np.ndarray) else article['_embedding']  
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        return True
    except IOError:
        return False

def clean_expired_cache(cache_data):
    """Remove cache entries older than 7 days."""
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)
    cutoff_timestamp = cutoff_date.isoformat()
    
    cleaned_articles = []
    for article in cache_data.get("articles", []):
        article_timestamp = article.get("timestamp", "")
        if article_timestamp > cutoff_timestamp:
            cleaned_articles.append(article)
    
    cache_data["articles"] = cleaned_articles
    return cache_data


def add_article_to_cache(cache_data, title, content, source_url):
    """Add a new article to the cache with its embedding."""
    #embedding = get_article_embedding(title, content)
    
    cache_entry = {
        "title": title,
        "content": content[:500],  # Store first 500 chars to save space
        "source_url": source_url,
        #"embedding": embedding,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    cache_data["articles"].append(cache_entry)
    return cache_data

def fetch_and_save_papers_rss_to_json():
    url = "https://papers.takara.ai/api/feed"
    response = requests.get(url)
    response.raise_for_status()
    root = ET.fromstring(response.content)

    items = []
    for item in root.findall('.//item'):
        title = item.findtext('title', default='').strip()
        content = re.sub(r'AI-generated summary.*', '', item.findtext('description', default='').strip())
        source_url = item.findtext('link', default='').strip().replace("https://tldr.takara.ai/p/", "https://arxiv.org/abs/")
        items.append({
            "title": title,
            "content": content,
            "source_url": source_url
        })
    articles = items
    with open("daily_papers.json", "w", encoding="utf-8") as f:
        json.dump({"articles": articles}, f, ensure_ascii=False, indent=2)


def load_reddit_token():
    """Load Reddit access token from .cass file."""
    try:
        with open('.cass', 'r') as f:
            token = f.read().strip()
        if not token:
            raise ValueError("Empty token in .cass file")
        return token
    except FileNotFoundError:
        print("Error: .cass file not found. Please create it with your Reddit access token.")
        return None
    except Exception as e:
        print(f"Error reading .cass file: {e}")
        return None

def get_reddit_posts(client):
    # Calculate the timestamp for yesterday
    yesterday = datetime.now().astimezone(timezone.utc) - timedelta(days=1)
    yesterday_timestamp = int(yesterday.timestamp())
    global input_tokens, output_tokens
    
    # Load Reddit access token from .cass file
    reddit_token = load_reddit_token()
    if not reddit_token:
        print("Skipping Reddit posts - no valid token available")
        return []

    # Fetch posts from the Reddit API that contains text in the description
    url = f"https://oauth.reddit.com/r/LocalLLaMa/top.json?t=day&limit=200&after={yesterday_timestamp}&q=text"
    headers = {
        'User-Agent': 'news_updates/0.1 by u/mahnehga',
        'Authorization': f'Bearer {reddit_token}'
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    posts = response.json().get('data', {}).get('children', [])
    posts = [post for post in posts if post.get('data', {}).get('selftext', '')]
    # Initialize the zero-shot classification pipeline
    # Filter posts with flair "News", "Discussion", "New Model"
    classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
    #discussion_posts = [post for post in posts if post.get('data', {}).get('link_flair_text', '') in ["Discussion"]]

    
    news_posts = [post for post in posts if post.get('data', {}).get('link_flair_text', '') in ["News", "New Model"]]
    for post in news_posts:
        classification = classifier(post.get('data', {}).get('title', '') + "\n\n" + post.get('data', {}).get('selftext', ''),["Current News/Happening/Updates"])
        post['data']['classification_score'] = classification['scores'][0]
    #sort posts by classification score, and score + comments
    posts = sorted(news_posts, key=lambda x: (x.get('data', {}).get('score', 0) + x.get('data', {}).get('num_comments', 0)), reverse=True)
    #import pdb;pdb.set_trace()
    posts = posts[:10]
    
    
    articles = []

    for post in posts:
        post_data = post.get('data', {})
        title = post_data.get('title', '')
        content =  post_data.get('title', '') + "\n\n" + post_data.get('selftext', '')
        # summarize content to one line 
        # use llm to summarize content
        summary = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=content,
            config=GenerateContentConfig(
                response_modalities=["TEXT"],
                max_output_tokens=100,
                system_instruction="Summarize the provided news content into a concise, professional paragraph. Try to avoid a conversational tone, and technical language. Focus on key insights, implications, and data points"
            )
        )
        # Count model tokens
        input_tokens += summary.usage_metadata.prompt_token_count
        output_tokens += summary.usage_metadata.candidates_token_count
        #images = [media.get('oembed', {}).get('thumbnail_url', '') for media in post_data.get('media_metadata', {}).values()] if post_data.get('media_metadata') else []
        link = 'https://reddit.com' + post_data.get('permalink', '')
        #date_posted = datetime.utcfromtimestamp(post_data.get('created_utc', 0)).strftime('%Y-%m-%d %H:%M:%S')
        summary_text = summary.candidates[0].content.parts[0].text
        # Classify the post
    
        articles.append({
            #"date_posted": date_posted,
            "title": title,
            "content": summary_text,
            "source_url": link
        })
    
    # Save articles to file (even if empty list)
    with open("reddit_news.json", "w", encoding="utf-8") as f:
        json.dump({"articles": articles}, f, ensure_ascii=False, indent=2)
    
    print(f"Saved {len(articles)} Reddit articles to reddit_news.json")
    return articles





### SMOL AI NEWS VARIABLES AND FUNCTIONS
SMOL_AI_BASE_URL = "https://news.smol.ai/"

# --- Configuration for Scraping Logic ---

# 1. Keywords to identify sub-sections to EXCLUDE within the Twitter Recap
TWITTER_SUBSECTIONS_TO_EXCLUDE = [
    "research, evaluation, and ai safety",
    "industry trends, talent & companies",
    "company strategy and the industry landscape",
    "humor, memes, and culture",
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
            quote_title = quote(strong_tag.get_text(strip=True).strip())
            strong_tag.extract()  # Remove the title part to get the content
            content = li.get_text(strip=True)
            
            if title and content:
                items.append({
                    "title": title,
                    "content": content,
                    "source_url": source_url+":~:text="+quote_title
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

def get_latest_headlines_url(session,req_date):
    resp = fetch_url(session, AI_NEWS_BASE_URL)
    soup = BeautifulSoup(resp.text, "html.parser")
    for blk in soup.select("div.flex-col.flex"):
        if blk.find("h4", string=lambda t: t and "Top AiNews.com Headlines" in t):
            a = blk.find("a", href=True)
            if req_date in blk.parent.get_text():return urljoin(AI_NEWS_BASE_URL, a["href"])
            return None
    raise RuntimeError("Could not find the Top AiNews.com Headlines link.")

def parse_list_items(ul):
    """Given a <ul>, return list of {title, content, source_url} from its <li>s."""
    out = []
    current_utc_time = datetime.now().astimezone(timezone.utc)
  #  today_utc_date_str = current_utc_time.strftime("%Y-%m-%d")
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
#            "date_scraped":today_utc_date_str
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
    # Load cache and clean expired entries
    cache_data = load_cache()
    cache_data = clean_expired_cache(cache_data)
    
    # First, collect all articles from all sources
    all_today_articles = []
    source_files = [
        "reddit_news.json",
        #"daily_papers.json", 
        #"shapiroainews.json",
        #"smolainews.json",
        "rss_news.json"
    ]
    
    for source_file in source_files:
        if os.path.exists(source_file):
            with open(source_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                articles = data.get("articles", [])
                for article in articles:
                    article["source_file"] = source_file  # Track which file it came from
                    all_today_articles.append(article)
    
    print(f"Collected {len(all_today_articles)} articles from all sources")
    
    # Step 1: Remove duplicates within today's articles (preliminary check)
    # Precompute embeddings for all articles upfront
    model = get_embedding_model()
    combined_texts = [article.get('title', '') for article in all_today_articles]
    # Compute embeddings in batch
    all_embeddings = model.encode(combined_texts)
    # Attach embedding to each article for deduplication
    for article, embedding in zip(all_today_articles, all_embeddings):
        article["_embedding"] = embedding

    unique_today_articles = []
    today_skipped = 0

    for i, article in enumerate(all_today_articles):
        title = article.get("title", "")
        content = article.get("content", "")
        source_url = article.get("source_url", "")
        embedding = np.array(article["_embedding"]).reshape(1, -1)

        # Check against other articles collected today
        is_duplicate_today = False
        for j, existing_article in enumerate(unique_today_articles):
            existing_title = existing_article.get("title", "")
            existing_content = existing_article.get("content", "")
            existing_url = existing_article.get("source_url", "")
            existing_embedding = np.array(existing_article["_embedding"]).reshape(1, -1)
            if i==j:
                continue
            # Check URL match first (fastest)
            if source_url and existing_url and source_url == existing_url and "https://news.smol.ai" not in source_url:
                is_duplicate_today = True
                print(f"Skipped today's duplicate (URL match): {title[:60]}...")
                break

            # Check content similarity
            if title and content and existing_title and existing_content:
                similarity = cosine_similarity(embedding, existing_embedding)[0][0]
                if similarity >= 0.81:  # Same threshold as cache check
                    is_duplicate_today = True
                    print(f"Skipped today's duplicate (similarity {similarity:.3f}): {title[:60]}...")
                    break

        if not is_duplicate_today:
            unique_today_articles.append(article)
        else:
            today_skipped += 1

    print(f"After preliminary deduplication: {len(unique_today_articles)} unique articles, skipped {today_skipped} today's duplicates")

    # Step 2: Check against cache for historical duplicates
    combined_output = {"articles": []}
    cache_skipped = 0

    for article in unique_today_articles:
        title = article.get("title", "")
        content = article.get("content", "")
        source_url = article.get("source_url", "")

        # Check if article is similar to cached articles
        is_similar = False
        reason="unbound"
        for cached_article in cache_data["articles"]:
            if cached_article.get("title") == title and cached_article.get("content") == content:
                is_similar = True
                reason = "title and content match"
                break
            if cached_article.get("source_url") == source_url:
                is_similar = True
                reason = "source_url match"
                break
            if cosine_similarity(np.array(cached_article.get("_embedding")).reshape(1, -1),np.array(article.get("_embedding")).reshape(1, -1))[0][0] >= 0.81:
                is_similar = True
                reason = "embedding match"
                break
        
        if not is_similar:
            # Remove the source_file tracking before adding to output
            article_copy = {k: v for k, v in article.items() if k != "source_file"}
            article_copy['_embedding'] = article_copy['_embedding'].tolist() if isinstance(article_copy['_embedding'], np.ndarray) else article_copy['_embedding']
            combined_output["articles"].append(article_copy)
            print(f"Added article: {title[:60]}...")
        else:
            cache_skipped += 1
            print(f"Skipped cached duplicate ({reason}): {title[:60]}...")

    print(f"Final result: {len(combined_output['articles'])} articles, skipped {today_skipped} today's duplicates + {cache_skipped} cached duplicates")

    # Save the combined output to a new file
    with open("ai_news.json", "w", encoding="utf-8") as f:

        json.dump(combined_output, f, ensure_ascii=False, indent=2)

    # Save updated cache
    save_cache(cache_data)


def clean_and_overwrite_articles(filepath: str):
    """
    Loads articles from a JSON file, cleans their content, and overwrites the file.
    
    Cleaning steps:
    1. Removes patterns like "(Score: 123, Comments: 45): " from the start of content.
    2. Removes any leading colons from the content.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            original_articles = data.get("articles", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return False

    # Regex to find "(Score: ..., Comments: ...):" at the start of the string
    score_comment_pattern = re.compile(r'^\(Score: \d+,\s*Comments: \d+\):?\s*')
    
    cleaned_articles = []
    for article in original_articles:
        if 'content' in article and isinstance(article['content'], str):
            content = article['content']
            # Apply regex substitution to remove score/comment pattern
            content = score_comment_pattern.sub('', content)
            # Remove leading colon and any extra whitespace from the result
            content = content.lstrip(':').strip()
            # Update the article's content
            article['content'] = content
        cleaned_articles.append(article)

    # Create the final JSON structure with cleaned articles
    output_data = {"articles": cleaned_articles}

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
        return True
    except IOError:
        return False


def rank_articles_by_importance(client, articles):
    """Rank articles by importance/relevance and return scored list."""
    global input_tokens, output_tokens
    
    ranking_prompt = """
You are an expert AI news curator. Rate this article's importance for AI/ML developers on a scale of 1-10.

**HIGH IMPORTANCE (8-10):**
- Major model releases (GPT, Claude, Llama, etc.)
- Breakthrough research with immediate practical impact
- New open-source tools that developers will use
- Significant performance benchmarks or evaluations
- Major infrastructure/platform updates

**MEDIUM IMPORTANCE (5-7):**
- Incremental improvements to existing tools
- Interesting research with potential future impact
- Company AI strategy announcements with technical details
- Industry analysis with actionable insights

**LOW IMPORTANCE (1-4):**
- Pure business news (funding, acquisitions)
- High-level strategy without technical content
- Routine product updates
- Generic AI adoption stories

Respond with ONLY a number from 1-10. No explanation needed.
"""
    
    scored_articles = []
    
    for article in articles:
        title = article.get("title", "")
        content = article.get("content", "")
        
        prompt = f"Title: {title}\n\nContent: {content[:400]}"
        
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=GenerateContentConfig(
                    response_modalities=["TEXT"],
                    max_output_tokens=5,
                    temperature=0,
                    system_instruction=ranking_prompt
                )
            )
            
            input_tokens += response.usage_metadata.prompt_token_count
            output_tokens += response.usage_metadata.candidates_token_count
            
            score_text = response.candidates[0].content.parts[0].text.strip()
            try:
                score = float(score_text)
                score = max(1, min(10, score))  # Clamp to 1-10 range
            except ValueError:
                score = 5  # Default score if parsing fails
                
            scored_articles.append({
                'article': article,
                'score': score
            })
            print(f"  Score {score}/10: {title[:60]}...")
            
        except Exception as e:
            print(f"Error scoring article '{title[:40]}': {e}")
            scored_articles.append({
                'article': article,
                'score': 5  # Default score
            })
            
        time.sleep(0.5)  # Rate limiting
    
    # Sort by score (highest first)
    scored_articles.sort(key=lambda x: x['score'], reverse=True)
    return scored_articles

def select_diverse_articles(scored_articles, target_count=5):
    """Select top articles ensuring source and topic diversity."""
    if len(scored_articles) <= target_count:
        return [item['article'] for item in scored_articles]
    
    selected = []
    used_sources = set()
    
    # First pass: Take highest scoring articles from different sources
    for item in scored_articles:
        if len(selected) >= target_count:
            break
            
        article = item['article']
        source_url = article.get('source_url', '')
        
        # Extract domain from URL for diversity check
        try:
            domain = urlparse(source_url).netloc.lower()
            domain = domain.replace('www.', '')  # Normalize
        except:
            domain = source_url
        
        # Skip if we already have 2 articles from this source
        source_count = sum(1 for selected_article in selected 
                          if urlparse(selected_article.get('source_url', '')).netloc.lower().replace('www.', '') == domain)
        
        if source_count < 2:  # Max 2 articles per source
            selected.append(article)
            used_sources.add(domain)
            print(f"  ✓ Selected (score {item['score']}): {article.get('title', '')[:60]}...")
        else:
            print(f"  ⚠ Skipped for diversity (score {item['score']}): {article.get('title', '')[:60]}...")
    
    # Second pass: Fill remaining slots with highest scoring articles
    if len(selected) < target_count:
        for item in scored_articles:
            if len(selected) >= target_count:
                break
            if item['article'] not in selected:
                selected.append(item['article'])
                print(f"  ✓ Added to fill quota (score {item['score']}): {item['article'].get('title', '')[:60]}...")
    
    return selected[:target_count]

def filter_ai_news_from_file(client, model_id, input_filepath: str):
    """
    Loads cleaned articles, deduplicates by title, filters them for a developer/business
    audience using an LLM, ranks by importance, and selects top 5 diverse articles.
    
    Args:
        client: Google GenAI client instance
        model_id: Model ID (gemini-2.0-flash)
        input_filepath: Path to input JSON file
    """
    output_filepath = "filtered_ai_news.json"
    
    # --- Setup and Configuration ---
    global input_tokens, output_tokens

    # Updated system prompt focusing on content and specific criteria
    system_prompt = """
You are an expert AI news curator for a highly technical audience of AI/ML developers, business professionals, and researchers. Your primary task is to analyze the **article content** to make your decision.

**KEEP articles if their content is about:**
- New LLMs, foundational models, or significant model updates (e.g., new position on a leaderboard).
- Technical discussions about AI, MCP, UTCP, or related infrastructure.
- New or updated open-source AI tools, libraries, or evaluation frameworks like Graph RAG.
- Practical evaluations or comparisons of generative AI tools.
- Significant research breakthroughs with clear technical implications for developers.
- Tools which can help in daily office work or tasks or can help technically.
- Business news or announcements that are relevant to AI/ML developers or business professionals.

**DISCARD articles if their content is primarily about:**
- Purely business news: funding rounds, investments, valuations, or company acquisitions.
- General company announcements, marketing, or promotional content.
- High-level 'AI in business' use cases without technical details or business insights.
- AI policy, regulation discussions, or generic CEO interviews.
- Announcements of training programs, cohorts, or educational courses.
- Entertainment, memes, NSFW, or adult content.

Your response MUST be a single word: either KEEP or DISCARD. Do not add any explanation or punctuation.
"""

    # Google client is passed as parameter, no need to initialize
    # --- Load and Deduplicate Articles by Title ---
    try:
        with open(input_filepath, "r", encoding="utf-8") as f:
            all_articles = json.load(f).get("articles", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return

    try:
        with open(output_filepath, "r", encoding="utf-8") as f:
            yesterday_articles = json.load(f).get("articles", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return
    yesterday_articles= [x['source_url'] for x in yesterday_articles]
    unique_articles = []
    seen_titles = set()
    seen_links = set()
    for article in all_articles:
        title = article.get("title")
        if title:
            normalized_title = title.lower().strip()
            if normalized_title and normalized_title not in seen_titles and article.get("source_url") not in seen_links:
                unique_articles.append(article)
                seen_titles.add(normalized_title)


    # --- Filter Articles with LLM ---
    print(f"\n=== Filtering {len(unique_articles)} articles for AI relevance ===")
    developer_focused_articles = []
    
    for article in unique_articles:
        title = article.get("title", "No Title")
        content = article.get("content", "")

        # The LLM will now primarily judge based on the cleaned content
        full_prompt = f"{system_prompt}\n\nTitle: {title}\n\nContent: {content}"

        try:
            response = client.models.generate_content(
                model=model_id,
                contents=full_prompt,
                config=GenerateContentConfig(
                    response_modalities=["TEXT"],
                    maxOutputTokens=50,
                    temperature=0
                )
            )
            
            # Count model tokens for cost tracking
            input_tokens += response.usage_metadata.prompt_token_count
            output_tokens += response.usage_metadata.candidates_token_count
            
            decision = response.candidates[0].content.parts[0].text.strip().upper()
            if decision == "KEEP":
                developer_focused_articles.append(article)
                print(f"  ✓ Kept: {title[:60]}...")
            else:
                print(f"  ✗ Discarded: {title[:60]}...")
                
        except Exception as e:
            print(f"  Error filtering '{title[:40]}': {e}")
            continue
    
    print(f"\n=== Found {len(developer_focused_articles)} relevant articles ===")
    
    # --- Rank Articles by Importance ---
    if len(developer_focused_articles) > 5:
        print(f"\n=== Ranking articles by importance ===")
        scored_articles = rank_articles_by_importance(client, developer_focused_articles)
        
        print(f"\n=== Selecting top 5 diverse articles ===")
        final_articles = select_diverse_articles(scored_articles, target_count=5)
        
        print(f"\n=== Selected {len(final_articles)} final articles ===")
    else:
        # If we have 5 or fewer, keep them all
        final_articles = developer_focused_articles
        print(f"Using all {len(final_articles)} articles (≤5 found)")
    
    # --- Save Filtered Articles to a New JSON File ---
    output_data = {"articles": final_articles}

    save_cache(output_data)
    try:
        with open(output_filepath, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
    except IOError as e:
        raise IOError(f"Error writing to file {output_filepath}: {e}")


def parse_feed_date(date_str):
    """Parse various RSS date formats and return datetime object."""
    if not date_str:
        return None
        
    # Common RSS date formats
    date_formats = [
        "%a, %d %b %Y %H:%M:%S %z",  # RFC 2822 format
        "%a, %d %b %Y %H:%M:%S %Z",  # RFC 2822 with timezone name
        "%Y-%m-%dT%H:%M:%S%z",       # ISO 8601 with timezone
        "%Y-%m-%dT%H:%M:%SZ",        # ISO 8601 UTC
        "%Y-%m-%d %H:%M:%S",         # Simple format
        "%a, %d %b %Y %H:%M:%S GMT", # GMT format
        "%Y-%m-%dT%H:%M:%S.%f%z",    # ISO with microseconds and timezone
        "%Y-%m-%dT%H:%M:%S.%fZ",     # ISO with microseconds UTC
    ]
    
    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            # If no timezone info, assume UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    
    # Try parsing with dateutil as fallback
    try:
        from dateutil import parser
        dt = parser.parse(date_str)
        # If no timezone info, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except:
        pass
    
    print(f"Warning: Could not parse date '{date_str}'")
    return None

def parse_rss_feeds(client):
    """Parse RSS feeds from feeds.txt and extract AI-related articles."""
    global input_tokens, output_tokens
    
    # Calculate the timestamp for past 24 hours
    yesterday = datetime.now().astimezone(timezone.utc) - timedelta(days=1)
    print(f"Filtering articles published after: {yesterday.isoformat()}")
    
    # Load RSS feeds from file
    try:
        with open("feeds.txt", "r") as f:
            feeds = [line.strip() for line in f.readlines() if line.strip()]
    except FileNotFoundError:
        print("feeds.txt not found")
        return []
    
    # Define feed categories
    AI_SPECIFIC_FEEDS = {
        "https://analyticsindiamag.com/feed/",
        "https://knowtechie.com/category/ai/feed/",
        "https://www.artificialintelligence-news.com/feed/rss/",
        "https://venturebeat.com/category/ai/feed/",
        "https://siliconangle.com/category/ai/feed",
        "https://aibusiness.com/rss.xml", 
        "https://www.theguardian.com/technology/artificialintelligenceai/rss",
        "https://www.wired.com/feed/tag/ai/latest/rss",
        "https://aimodels.substack.com/feed",
        "https://www.normaltech.ai/feed",
        "https://www.marktechpost.com/feed"
    }
    
    GENERAL_FEEDS = {
        "https://www.404media.co/rss",
        "https://feeds.arstechnica.com/arstechnica/index",
        "https://feeds.businessinsider.com/custom/all",
        "https://www.sify.com/feed/"
    }
    
    # Skip problematic feeds
    SKIP_FEEDS = {
        "https://magazine.sebastianraschka.com/feed", 
        "https://aiacceleratorinstitute.com/rss/",
        "https://www.quantamagazine.org/feed"
    }
    
    all_articles = []
    
    for feed_url in feeds:
        if feed_url in SKIP_FEEDS:
            print(f"Skipping problematic feed: {feed_url}")
            continue
            
        try:
            print(f"Processing feed: {feed_url}")
            feed_response = requests.get(feed_url,impersonate="chrome")
            # Use feedparser to parse the feed
            feed = feedparser.parse(feed_response.content)
            
            if feed.bozo:
                print(f"Warning: Feed {feed_url} has parsing issues: {feed.bozo_exception}")
            
            articles = []
            
            for entry in feed.entries:
                title = getattr(entry, 'title', '').strip()
                
                # Get content from various possible fields
                content = ''
                if hasattr(entry, 'content') and entry.content:
                    content = entry.content[0] if isinstance(entry.content, list) else entry.content
                    if content.type == "text/html":
                        content = BeautifulSoup(content.value, 'html.parser').get_text()
                    else: content = content.value
                elif hasattr(entry, 'summary'):
                    content = entry.summary
                elif hasattr(entry, 'description'):
                    content = entry.description
                
                link = getattr(entry, 'link', '').strip()
                
                # Get published date
                pub_date = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    pub_date = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
                
                # Filter by date (past 24 hours only)
                if pub_date and pub_date < yesterday:
                    continue  # Skip articles older than 24 hours
                
                # Clean HTML from content
                content = re.sub(r'<[^>]+>', '', content) if content else ''
                
                if title and content and link:
                    articles.append({
                        "title": title,
                        "content": content[:500],  # Limit content length
                        "source_url": link
                    })
            
            print(f"Found {len(articles)} articles from {feed_url}")
            
            # Filter articles based on feed type
            if feed_url in AI_SPECIFIC_FEEDS:
                # AI-specific feeds - include all articles
                all_articles.extend(articles)
                print(f"Added all {len(articles)} articles from AI-specific feed")
            elif feed_url in GENERAL_FEEDS:
                # General feeds - check categories first, then use LLM for remaining
                ai_articles_from_categories = []
                remaining_articles = []
                
                # Extract categories from original feed entries and check for AI-related terms
                ai_category_terms = {
                    'ai', 'artificial intelligence', 'machine learning', 'ml', 'deep learning',
                    'neural network', 'neural networks', 'chatgpt', 'gpt', 'gpt-4', 'gpt-3',
                    'llm', 'large language model', 'large language models', 'transformer',
                    'computer vision', 'nlp', 'natural language processing', 'robotics',
                    'automation', 'openai', 'anthropic', 'google ai', 'microsoft ai',
                    'ai research', 'ai technology', 'ai tools', 'generative ai', 'gen ai',
                    'claude', 'gemini', 'llama', 'hugging face', 'tensorflow', 'pytorch',
                    'stable diffusion', 'midjourney', 'dall-e', 'ai model', 'ai models',
                    'data science', 'predictive analytics', 'supervised learning',
                    'unsupervised learning', 'reinforcement learning', 'ai ethics',
                    'ai safety', 'agi', 'artificial general intelligence', 'ai chips',
                    'gpu', 'nvidia ai', 'ai hardware', 'ai software', 'ai startup',
                    'ai company', 'machine intelligence'
                }
                
                for i, article in enumerate(articles):
                    is_ai_by_category = False
                    
                    # Check if we can find the corresponding feed entry to get categories
                    if i < len(feed.entries):
                        entry = feed.entries[i]
                        categories = []
                        
                        # Extract categories from different possible fields
                        try:
                            if hasattr(entry, 'tags') and entry.tags:
                                for tag in entry.tags:
                                    if hasattr(tag, 'term') and tag.term:
                                        categories.append(tag.term.lower())
                                    elif hasattr(tag, 'label') and tag.label:
                                        categories.append(tag.label.lower())
                                    elif isinstance(tag, str):
                                        categories.append(tag.lower())
                                    else:
                                        categories.append(str(tag).lower())
                            
                            if hasattr(entry, 'categories') and entry.categories:
                                for cat in entry.categories:
                                    if isinstance(cat, str):
                                        categories.append(cat.lower())
                                    elif hasattr(cat, 'term'):
                                        categories.append(cat.term.lower())
                                    else:
                                        categories.append(str(cat).lower())
                            
                            if hasattr(entry, 'category') and entry.category:
                                categories.append(str(entry.category).lower())
                        except Exception as e:
                            print(f"    Warning: Error extracting categories for article: {e}")
                        
                        # Check if any category matches AI-related terms
                        for category in categories:
                            if any(ai_term in category for ai_term in ai_category_terms):
                                is_ai_by_category = True
                                print(f"  ✓ AI by category '{category}': {article.get('title', '')[:60]}...")
                                break
                    
                    # If no AI category found, check title and content as fallback
                    if not is_ai_by_category:
                        title = article.get('title', '').lower()
                        content = article.get('content', '').lower()
                        text_to_check = f"{title} {content}"
                        
                        # Check for AI terms in title/content (more strict matching for text)
                        strict_ai_terms = {
                            'artificial intelligence', 'machine learning', 'deep learning',
                            'chatgpt', 'gpt-4', 'gpt-3', 'openai', 'anthropic', 'claude',
                            'large language model', 'neural network', 'computer vision',
                            'natural language processing', 'generative ai'
                        }
                        
                        for ai_term in strict_ai_terms:
                            if ai_term in text_to_check:
                                is_ai_by_category = True
                                print(f"  ✓ AI by content term '{ai_term}': {article.get('title', '')[:60]}...")
                                break
                    
                    if is_ai_by_category:
                        ai_articles_from_categories.append(article)
                    else:
                        remaining_articles.append(article)
                
                # Use LLM to classify remaining articles
                ai_articles_from_llm = filter_articles_for_ai_content(client, remaining_articles, feed_url)
                
                # Combine results
                total_ai_articles = ai_articles_from_categories + ai_articles_from_llm
                all_articles.extend(total_ai_articles)
                print(f"Added {len(total_ai_articles)} AI-related articles from general feed ({len(ai_articles_from_categories)} by category, {len(ai_articles_from_llm)} by LLM)")
            else:
                # Unknown feeds - conservative filtering
                ai_articles = filter_articles_for_ai_content(client, articles, feed_url)
                all_articles.extend(ai_articles)
                print(f"Added {len(ai_articles)} AI-related articles from unknown feed")
                
        except Exception as e:
            print(f"Error processing feed {feed_url}: {e}")
            continue
    
    return all_articles

def filter_articles_for_ai_content(client, articles, feed_url):
    """Filter articles for AI-related content using LLM classification."""
    global input_tokens, output_tokens
    
    if not articles:
        return []
    
    ai_articles = []
    
    system_prompt = """
    You are an expert AI content classifier. Your task is to determine if a news article is related to artificial intelligence, machine learning, or AI technology.

    INCLUDE articles about:
    - AI research, models, algorithms, techniques
    - Machine learning breakthroughs and applications  
    - Large language models, ChatGPT, GPT, Claude, etc.
    - AI companies, startups, investments in AI
    - AI ethics, regulation, safety
    - Computer vision, natural language processing
    - Robotics and automation
    - AI tools and applications
    - Neural networks, deep learning
    - AI in specific industries (healthcare AI, autonomous vehicles, etc.)

    EXCLUDE articles about:
    - General technology news unrelated to AI
    - Pure business news without AI focus
    - Politics, sports, entertainment (unless AI-related)
    - Traditional software development
    - Hardware reviews (unless AI-specific)
    - General science news without AI connection

    Respond with only 'YES' if the article is AI-related, or 'NO' if it is not. No explanation needed.
    """
    
    for article in articles[:10]:  # Limit to first 10 articles per feed to control costs
        title = article.get("title", "")
        content = article.get("content", "")
        
        prompt = f"Title: {title}\n\nContent: {content[:300]}"  # Limit content to reduce costs
        
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=GenerateContentConfig(
                    response_modalities=["TEXT"],
                    maxOutputTokens=5,
                    temperature=0,
                    system_instruction=system_prompt
                )
            )
            
            input_tokens += response.usage_metadata.prompt_token_count
            output_tokens += response.usage_metadata.candidates_token_count
            
            decision = response.candidates[0].content.parts[0].text.strip().upper()
            
            if decision == "YES":
                ai_articles.append(article)
                print(f"  ✓ AI article: {title[:60]}...")
            else:
                print(f"  ✗ Not AI: {title[:60]}...")
                
        except Exception as e:
            print(f"Error classifying article '{title[:40]}': {e}")
            continue
            
        # Add small delay to respect rate limits
        time.sleep(0.5)
    
    return ai_articles

def main():
    """
    Main function to run for AI news.
    """
    global total_cost
    load_dotenv()
    #GITHUB_TRENDING_URL = "https://github.com/trending"
    #REPO_OUTPUT_FILE = "trending_repos.json"


    ## smol ai news
    #latest_issue_url = get_latest_issue_url()

    # Use timezone-aware datetime with .now() and datetime.timezone.utc
    
    yesterday = datetime.now().astimezone(timezone.utc) - timedelta(days=1)

    # format time to string
    yesterday_str = yesterday.strftime("%y-%m-%d")
    """
    if latest_issue_url and yesterday_str in latest_issue_url:
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
    else:
        if os.path.exists("smolainews.json"):
            os.remove("smolainews.json")
    """
    ## ai news
    session = requests.Session()
    session.headers.update(HEADERS)
    # if os.path.exists("shapiroainews.json"):
    #     os.remove("shapiroainews.json")
    # if os.path.exists("smolainews.json"):
    #     os.remove("smolainews.json")
    # if os.path.exists("ai_news.json"):
    #     os.remove("ai_news.json")
    # if os.path.exists("filtered_ai_news.json"):
    #     os.remove("filtered_ai_news.json")

    #Fetching homepage
    yesterday_formatted = yesterday.strftime("%b %d, %Y")
    latest_url = get_latest_headlines_url(session,yesterday_formatted)

    if latest_url:
    #Downloading article
        resp = fetch_url(session, latest_url)
        soup = BeautifulSoup(resp.text if resp is not None else "", "html.parser")

        #Extracting Today’s Headlines (only today's items; exclude AI Tools which can be older)
        todays = extract_section(soup, section_id="todays-headlines", stop_id="ai-tools")

        # Exclude AI Tools from aggregation to avoid pulling in prior-day items
        all_articles = todays

        with open("shapiroainews.json", "w", encoding="utf-8") as f:
            json.dump({"articles": all_articles}, f, ensure_ascii=False, indent=2)
    
    else:
        if os.path.exists("shapiroainews.json"):
            os.remove("shapiroainews.json")

    #time.sleep(10)
    # Create combined output

    # Initialize Google AI client
    google_api_key = os.getenv("GOOGLE_API_KEY")
    model_id = "gemini-2.0-flash"
    client = genai.Client(api_key=google_api_key)

    get_reddit_posts(client)
    fetch_and_save_papers_rss_to_json()

    # Parse RSS feeds and save to file
    print("\n=== Processing RSS Feeds ===")
    rss_articles = parse_rss_feeds(client)
    if rss_articles:
        with open("rss_news.json", "w", encoding="utf-8") as f:
            json.dump({"articles": rss_articles}, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(rss_articles)} RSS articles to rss_news.json")
    else:
        print("No RSS articles found")

    # search AI news only if ai_news.json has less than 10 articles
    #combined_news_path = "ai_news.json"
    #run_search_ai_news = True
    #if os.path.exists(combined_news_path):
    #    try:
    #        with open(combined_news_path, "r", encoding="utf-8") as f:
    #            data = json.load(f)
    #            articles = data.get("articles", [])
    #            if len(articles) >= 10:
    #                run_search_ai_news = False
    #    except Exception:
    #        pass
    #if run_search_ai_news:
    #search_ai_news(client, model_id, yesterday_str)

    # scrape GitHub trending repositories
    create_combined_output()

    # Define the path to your single news file
    news_json_file = "ai_news.json"
    total_cost +=1e-07*input_tokens + 4e-07*output_tokens
    # Check for required files before starting
    if os.path.exists(news_json_file):
        # Step 1: Clean the source file in place.
        # The function returns False if it fails, so we can stop the process.
        if clean_and_overwrite_articles(news_json_file):
            # Step 2: Run the filtering process on the now-cleaned file.
            filter_ai_news_from_file(client, model_id, news_json_file)
    print(f"Input tokens: {input_tokens}")
    print(f"Output tokens: {output_tokens}")
    print(f"Total cost: ${total_cost:.6f}")


if __name__ == "__main__":
    main()
