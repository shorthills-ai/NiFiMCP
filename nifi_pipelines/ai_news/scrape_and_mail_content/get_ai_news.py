import os
import sys
from pathlib import Path
import json
from langchain.schema import AIMessage, HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI
from pydantic import SecretStr
import datetime
import requests
from dotenv import load_dotenv
from langchain_community.callbacks import get_openai_callback as openai_callback
import urllib.parse
total_cost = 0
load_dotenv()

# Prepare today's date
today_str = datetime.date.today().strftime("%B %d, %Y")
week_str = f"{ (datetime.date.today() - datetime.timedelta(days=7)).strftime("%B %d, %Y") } - {today_str }"

base_dir = Path(__file__).resolve().parent
json_path = base_dir / "filtered_ai_news.json"
repo_json_path = base_dir / "trending_repos.json"

# Fetch recipients
recipients = os.getenv('AI_NEWS_RECIPIENTS')
recipients_data = json.loads(recipients)["toRecipients"]

# Initialize LLM
llm = AzureChatOpenAI(
        model="gpt-4o-mini",
        api_version='2024-12-01-preview',
        azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT', ''),
        api_key=SecretStr(os.getenv('AZURE_OPENAI_KEY', '')),
        )
def get_thumbnail_url(source_url):
    """Get the thumbnail URL from the source URL with comprehensive error handling."""
    # Default fallback image URL
    fallback_url = "https://arxiv.org/static/browse/0.3.4/images/arxiv-logo-fb.png"
    
    # Validate input
    if not source_url or not isinstance(source_url, str):
        print(f"Warning: Invalid source_url provided: {source_url}")
        return fallback_url
    
    source_url = source_url.strip()
    if not source_url:
        print("Warning: Empty source_url provided")
        return fallback_url
    
    try:
        if "arxiv.org" in source_url:
            # get arxiv id with error handling
            try:
                arxiv_id = source_url.split("/")[-1]
                if arxiv_id:
                    return f"https://cdn-thumbnails.huggingface.co/social-thumbnails/papers/{arxiv_id}/gradient.png"
                else:
                    print(f"Warning: Could not extract arXiv ID from {source_url}")
                    return fallback_url
            except (IndexError, AttributeError) as e:
                print(f"Error extracting arXiv ID from {source_url}: {e}")
                return fallback_url
                
        elif ".jpeg" in source_url or ".png" in source_url or ".jpg" in source_url:
            return source_url
            
        elif "github.com" in source_url:
            try:
                repo_path = source_url.replace('https://github.com/', '')
                if repo_path and repo_path != source_url:  # Ensure replacement worked
                    return f"https://opengraph.githubassets.com/12e7c96052543eb3beff547811277a293e6d003a901ebf270312c9b352b4460e/{repo_path}"
                else:
                    print(f"Warning: Could not extract GitHub repo path from {source_url}")
                    return fallback_url
            except Exception as e:
                print(f"Error processing GitHub URL {source_url}: {e}")
                return fallback_url
                
        elif "reddit.com" in source_url:
            return f"https://share.redd.it/preview/post/1d04itt"
        elif "v.reddit.com" in source_url or "redd.it" in source_url:
            return f"https://share.redd.it/preview/post/1d04itt"
        else:
            # Handle OpenGraph API with comprehensive error handling
            try:
                # URI encode the source url with error handling
                try:
                    encoded_url = urllib.parse.quote(source_url, safe=':/?#[]@!$&\'()*+,;=')
                except Exception as e:
                    print(f"Error encoding URL {source_url}: {e}")
                    return fallback_url
                
                # Make HTTP request with timeout and error handling
                api_url = f"https://opengraph.io/api/1.1/site/{encoded_url}?app_id=f6ef4e6b-4162-40d7-8404-b80736d4bd55"
                
                try:
                    response = requests.get(api_url, timeout=10)
                    response.raise_for_status()  # Raises HTTPError for bad responses
                except requests.exceptions.Timeout:
                    print(f"Timeout fetching OpenGraph data for {source_url}")
                    return fallback_url
                except requests.exceptions.HTTPError as e:
                    print(f"HTTP error fetching OpenGraph data for {source_url}: {e}")
                    return fallback_url
                except requests.exceptions.ConnectionError:
                    print(f"Connection error fetching OpenGraph data for {source_url}")
                    return fallback_url
                except requests.exceptions.RequestException as e:
                    print(f"Request error fetching OpenGraph data for {source_url}: {e}")
                    return fallback_url
                
                # Parse JSON response with error handling
                try:
                    image_data = response.json()
                except json.JSONDecodeError as e:
                    print(f"JSON decode error for {source_url}: {e}")
                    return fallback_url
                
                # Extract image URL from nested structure with error handling
                try:
                    image_url = image_data["openGraph"]["image"]["url"]
                    if image_url and isinstance(image_url, str) and image_url.strip():
                        return image_url.strip()
                    else:
                        print(f"Empty or invalid image URL from OpenGraph for {source_url}")
                        return fallback_url
                except (KeyError, TypeError) as e:
                    print(f"Error extracting image URL from OpenGraph response for {source_url}: {e}")
                    print(f"Response structure: {image_data}")
                    return fallback_url
                    
            except Exception as e:
                print(f"Unexpected error processing {source_url}: {e}")
                return fallback_url
    
    except Exception as e:
        print(f"Unexpected error in get_thumbnail_url for {source_url}: {e}")
        return fallback_url

def get_news_highlights(json_path):
    """Fetches AI news highlights from json file generated after scraping/searching for AI news."""
    highlights = []
    titles = []
    contents = []
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return "Error: filtered_ai_news.json not found."
    except json.JSONDecodeError:
        return "Error: Could not decode filtered_ai_news.json."

    if "articles" in data and isinstance(data["articles"], list):
        for i, article in enumerate(data["articles"], 1):
            title = article.get("title", "N/A")
            source_url = article.get("source_url", "N/A")
            content = article.get("content", "N/A")
            thumbnail = get_thumbnail_url(source_url)
            highlight_entry = f'''
<div class="story-item">
    <div class="story-title">
        <a class="story-title" href="{source_url}">{title}</a>
        <img src="{thumbnail}" alt="Story thumbnail" class="story-thumbnail">
    </div>
    <div class="story-summary">
        {content}
    </div>
</div>'''.strip()
            highlights.append(highlight_entry)
            titles.append(title)
            contents.append(content)
    if not highlights:
        return "No articles found or articles are not in the expected format."
    
    highlights_joined = "\n\n".join(highlights)
    titles_joined = "||".join(titles)
    contents_joined = "\n".join(contents)

    return highlights_joined, titles_joined, contents_joined

def extract_takeaways_and_topics(titles_combined):
    global total_cost
    """
    Generate takeaways and topics using Azure OpenAI.

    Parameters:
        input_content (list): List of scraped content strings.
        azure_deployment_name (str): Name of your Azure OpenAI deployment.
        azure_api_base (str): Your Azure OpenAI endpoint (e.g., 'https://<your-resource-name>.openai.azure.com/').
        azure_api_key (str): Your Azure OpenAI API key.
        azure_api_version (str): API version (default '2023-05-15').

    Returns:
        str: AI News Summary generated by the LLM.
    """


    # Build prompt
    prompt = f"""
        You are an AI assistant tasked with extracting content for AI news. Create list of topics found in the input content.

        Here is the scraped content:

        {titles_combined}

        Note: Provide a clear, concise, and structured output as per the format.
        Follow this output format:
<h2>🗂️ Topics Covered</h2>
<p>
"Set of topics covered in the news separated by commas."
<p>
"""

    messages = [
                SystemMessage(
                    content="You are an AI assistant tasked with creating an AI News Summary for employees in an organization."
                ),
                HumanMessage(content=prompt),
            ]
    with openai_callback() as cb:
        response = llm.invoke(messages)
        total_cost += cb.total_cost
        print(f"Total cost: {total_cost}")
    # Extract response
    ai_news = response.content

    return ai_news

def sort_highlights(highlights_joined):
    global total_cost
    """
    Arranges the highlights into different sections based on topics.
    """
    prompt = f"""
You will be given a list of news highlights. Your task is to analyze these highlights and group them into logical sections based on recurring technologies, products, protocols, or major themes.

**Instructions:**

1.  **Identify Key Themes:** Read through all the highlights and identify the main subjects. Look for specific, recurring keywords that define a topic, from one of "Model Context Protocol (MCP)", "A2A", "Google", "Openai", "Antropic", "Llama" or "AI Agents", "AI Tools".
2.  **Create Section Headings:** Based on these themes, create clear and descriptive headings. Use html for the headings (e.g., '<h3>Model Context Protocol (MCP)</h3>'). The headings should be based on the specific technologies or products themselves.
3.  **Group the Highlights:** Place each original highlight under the most appropriate section heading.
4.  **Preserve Original Content:** Copy the highlights into the sections *exactly* as they are provided, including the content, its style and structure. Do not alter, re-summarize, or number them.
5.  **Be Logical:** Group items that are clearly related. For example, all news about MCP servers under single MCP-related heading, all news from google models and tools under google, similarly for any other organization.
6.  **Handle Other News:** For highlights that don't fit into a specific, recurring technology group, create a broader category '<h3>AI Developments</h3>'.

Here are the news highlights you need to sort:

---
{highlights_joined}
---

Please provide the sorted and categorized list of highlights below. The final output should be only the categorized news with no extra text or backtick, ready for a newsletter"""

    messages = [
                # The SystemMessage sets the overall context for the LLM's persona.
                SystemMessage(
                    content="You are an AI assistant tasked with sorting AI News for employees in an organization. You produce well-structured, clean output in Markdown format."
                ),
                # The HumanMessage contains the detailed instructions and the data.
                HumanMessage(content=prompt),
            ]

    with openai_callback() as cb:
        response = llm.invoke(messages)
        total_cost += cb.total_cost
    categorized_highlights = response.content   
    return categorized_highlights

def get_trending_repositories(repo_json_path):
    repositories = []
    try:
        with open(repo_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return "Error: trending_repos.json not found."
    except json.JSONDecodeError:
        return "Error: Could not decode trending_repos.json."

    if "repos" in data and isinstance(data["repos"], list):
        for i, article in enumerate(data["repos"], 1):
            #repo_name = article.get("repo_name", "N/A")
            #description = article.get("description", "N/A")
            source_url = article.get("repo_url", "N/A")
            
            repo_entry = f"""
        <div class="repo-item">
            <div class="repo-link"><a href="{source_url}"><img src="{get_thumbnail_url(source_url)}" alt="Story thumbnail" class="story-thumbnail"></a></div>
        </div>
        """
            repositories.append(repo_entry)

    
    if not repositories:
        return "No trending repos found."
    
    repositories_joined = "\n\n".join(repositories)

    return repositories_joined

def generate_quiz(ai_summary: str) -> tuple[str, dict]:

    """
    Generates an interactive HTML quiz with radio buttons based on the AI news summary.

    This function instructs an LLM to create a 10-question quiz in JSON format,
    then builds a self-contained HTML file with embedded CSS and JavaScript
    to provide immediate feedback to the user upon selecting a radio button.

    Args:
        ai_summary: A string containing the summarized content for the quiz.

    Returns:
        A tuple containing:
        - interactive_quiz (str): The full HTML code for the interactive quiz.
        - answer_key (dict): A dictionary mapping question numbers to correct answers (e.g., {1: 'A', 2: 'C'}).
    """
    global total_cost
    # 1. Updated prompt to request JSON output with answers (remains the same)
    prompt = f"""
        You are an AI quiz generator specializing in creating interactive learning content.
        Your task is to create a quiz of 10 questions based on the provided content.

        For each question, provide the question text, 4 multiple-choice options (A, B, C, D),
        and identify the letter of the correct answer.

        **IMPORTANT**: Respond ONLY with a valid JSON object. The JSON should be a list of objects,
        where each object has the following keys:
        - "question": A string for the question text.
        - "options": An object with keys "A", "B", "C", "D".
        - "answer": A string representing the key of the correct option (e.g., "A").

        Do not include any other text, greetings, or explanations outside of the JSON object.

        Here is the summarized content:
        {ai_summary}

        Example JSON output format:
        [
            {{
                "question": "What is the capital of France?",
                "options": {{
                    "A": "Paris",
                    "B": "London",
                    "C": "Berlin",
                    "D": "Madrid"
                }},
                "answer": "A"
            }},
            {{
                "question": "What is the largest planet in our solar system?",
                "options": {{
                    "A": "Earth",
                    "B": "Mars",
                    "C": "Jupiter",
                    "D": "Saturn"
                }},
                "answer": "C"
            }}
        ]
    """
    
    messages = [
        SystemMessage(content="You are an AI quiz generator specializing in JSON output."),
        HumanMessage(content=prompt),
    ]
    with openai_callback() as cb:
        response = llm.invoke(messages)
        total_cost += cb.total_cost
    llm_output = response.content
    cleaned_output = llm_output.replace("```json", "").replace("```", "").strip()

    try:
        quiz_data = json.loads(cleaned_output)
        # Save the valid quiz_data to quiz.json
        with open("quiz.json", "w", encoding="utf-8") as f:
            json.dump(quiz_data, f, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        raise ValueError("The LLM did not return valid JSON. Please check the input and try again.")

def generate_email_content(json_path,repo_json_path):
    """
    Generates the email content with a summary of AI news.
    """
    global input_tokens, output_tokens
    highlights_joined,titles_joined, contents_joined = get_news_highlights(json_path)
   # topic_takeaways = extract_takeaways_and_topics(titles_joined)
    titles_list = ''.join(f'<li>{line}</li>' for line in titles_joined.split("||") if line.strip())
    categorized_highlights = sort_highlights(highlights_joined)

    # get trending repositories
    trending_repos = get_trending_repositories(repo_json_path)

    # generate quiz
    generate_quiz(contents_joined)
    # set quiz url
    quiz = "<a href=http://104.208.162.61:8002/>Click here</a>"


    email_body = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Weekly Digest</title>
    <style>
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333333;
            margin: 0;
            padding: 0;
            background-color: #f8fafc;
            min-height: 100vh;
        }
        .container {
            max-width: 600px;
            margin: 20px auto;
            padding: 20px;
            background-color: #ffffff;
            border-radius: 8px;
            border: 1px solid #e5e7eb;
        }
        .header {
            text-align: center;
            padding: 20px 0;
            border-bottom: 1px solid #e5e7eb;
        }
        .header-links a {
            color: #2563eb;
            font-size: 18px;
            font-weight: 500;
            text-decoration: none;
            margin: 0 10px;
        }
        .header-links a:hover {
            text-decoration: underline;
        }
        .newsletter-thumbnail {
            width: 75%;
            height: auto;
            border-radius: 8px;
            margin: 15px auto;
            display: block;
            border: 1px solid #e5e7eb;
        }
        .logo {
            font-size: 28px;
            font-weight: 700;
            color: #1e293b;
            margin: 10px 0;
        }
        .greeting {
            font-size: 18px;
            color: #1f2937;
            margin: 20px 0;
        }
        .intro {
            font-size: 16px;
            color: #4b5563;
            background-color: #f1f5f9;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        h2 {
            font-size: 24px;
            font-weight: 600;
            color: #1e293b;
            margin: 30px 0 15px;
            border-bottom: 2px solid #3b82f6;
            padding-bottom: 8px;
        }
        h3 {
            font-size: 20px;
            font-weight: 600;
            color: #1f2937;
            margin: 20px 0 10px;
        }
        .story-item {
            margin-bottom: 20px;
            padding-bottom: 20px;
            border-bottom: 1px solid #e5e7eb;
        }
        .story-item:last-child {
            border-bottom: none;
        }
        .story-title {
            font-size: 21px;
            font-weight: 600;
            color: #2563eb;
            margin-bottom: 8px;
        }
        .story-title a {
            color: #2563eb;
            text-decoration: none;
        }
        .story-title a:hover {
            text-decoration: underline;
        }
        .story-summary {
            font-size: 18px;
            color: #4b5563;
            line-height: 1.5;
        }
        .story-thumbnail {
            width: 75%;
            height: auto;
            border-radius: 8px;
            margin-bottom: 12px;
            display: block;
            margin-left: auto;
            margin-right: auto;
            border: 1px solid #e5e7eb;
        }
        .repo-item {
            background-color: #f9fafb;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 3px solid #3b82f6;
        }
        .repo-title {
            font-size: 18px;
            font-weight: 600;
            color: #1e293b;
            margin-bottom: 8px;
        }
        .repo-description {
            font-size: 15px;
            color: #4b5563;
            margin-bottom: 10px;
        }
        .repo-link a {
            font-size: 14px;
            color: #2563eb;
            text-decoration: none;
        }
        .repo-link a:hover {
            text-decoration: underline;
        }
        .section-divider {
            height: 1px;
            background-color: #e5e7eb;
            margin: 30px 0;
        }
        .takeaways {
            background-color: #f1f5f9;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .takeaways ul {
            padding-left: 20px;
            margin: 10px 0;
        }
        .takeaways li {
            font-size: 15px;
            color: #4b5563;
            margin-bottom: 8px;
        }
        .quiz-section {
            background-color: #f1f5f9;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            margin-top: 20px;
        }
        .quiz-button {
            display: inline-block;
            background-color: #ff8200;
            color: #ffffff;
            padding: 10px 20px;
            border-radius: 20px;
            font-size: 15px;
            font-weight: 600;
            text-decoration: none;
        }
        .footer {
            text-align: center;
            padding: 20px 0;
            border-top: 1px solid #e5e7eb;
            font-size: 14px;
            color: #6b7280;
        }
        .footer strong {
            color: #1e293b;
        }
        .social-links {
            margin: 10px 0;
        }
        .social-links a {
            color: #2563eb;
            text-decoration: none;
            margin: 0 10px;
            font-size: 14px;
        }
        .social-links a:hover {
            text-decoration: underline;
        }
        .feedback {
            margin-top: 20px;
            font-size: 14px;
            color: #6b7280;
        }
        .feedback a {
            color: #2563eb;
            text-decoration: none;
            margin: 0 5px;
        }
        .feedback a:hover {
            text-decoration: underline;
        }
        /* Mobile Responsiveness */
        @media (max-width: 600px) {
            .container {
                padding: 15px;
                margin: 10px;
            }
            .logo {
                font-size: 24px;
            }
            h2 {
                font-size: 20px;
            }
            h3 {
                font-size: 18px;
            }
            .story-title {
                font-size: 16px;
            }
            .story-summary, .repo-description {
                font-size: 14px;
            }
            .quiz-button {
                font-size: 14px;
                padding: 8px 16px;
            }
        }
    </style>
</head>
"""+f"""<body>
    <div class="container">
        <div class="header">
            <img src="https://images.pexels.com/photos/8438918/pexels-photo-8438918.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940" alt="Newsletter thumbnail" class="newsletter-thumbnail">            
            <div class="logo">🤖 AI Daily Digest</div>
        </div>
        <div class="greeting">
            Good morning Shorthills Geeks!
        </div>
        <h2>News At a Glance</h2>
        <ul>
        {titles_list}
        </ul>
        <h2>News Articles</h2>
         {categorized_highlights}
        <hr class="section-divider">

        <h2>📦 Trending Repositories</h2>
        {trending_repos}
        <hr class="section-divider">
        <div class="quiz-section">
            <h3>🕒 Quick Quiz</h3>
            <a href="http://104.208.162.61:8002/" class="quiz-button">Test Your AI Knowledge</a>
        </div>
        <div class="footer">
            <div class="social-links">
                 </div>
            <p><strong>Best regards,</strong><br>
            <strong>AI News Team</strong><br>
            Shorthills AI</p>
            
        </div>
    </div>
</body>
</html>"""


    # Construct the dict object
    email_message = {
        "message": {
            "isReadReceiptRequested":True,
            "subject": "Daily AI News",
            "body": {
                "contentType": "HTML",
                "content": email_body
            },
            "toRecipients": recipients_data
        }
    }
   #print(email_body)
    # Serialize the whole structure as a valid JSON string
    template = json.dumps(email_message)

    return template


# ******************************************************************************************
# Usage: python get_ai_news_content.py <scraped_news_json_file>
# The JSON file should be the output from scrape_news.py
# ******************************************************************************************



if __name__ == "__main__":
    if len(sys.argv) == 2:
        json_path = Path(sys.argv[1])
    
    if not json_path.exists():
        sys.stderr.write(f"Expected news file not found at {json_path}\n")
        sys.exit(1)

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
    except Exception as e:
        sys.stderr.write(f"Error reading or parsing JSON: {str(e)}\n")
        sys.exit(1)
	
	
    email_body = generate_email_content(json_path,repo_json_path)
    print(email_body)
    # print(f"Total cost: ${total_cost:.6f}")
