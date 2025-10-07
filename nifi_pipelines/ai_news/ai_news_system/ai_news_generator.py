import os
import sys
from pathlib import Path
import json
from google import genai
from datetime import datetime
import requests
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
import urllib.parse
from typing import List, Dict, Any, Tuple
import hashlib
from PIL import Image
from io import BytesIO

# Load environment variables
load_dotenv()

# Initialize Gemini API
api_key = os.getenv('GOOGLE_API_KEY')
if not api_key:
    raise ValueError("GOOGLE_API_KEY environment variable is required")


# Setup directories
base_dir = Path(__file__).resolve().parent
templates_dir = base_dir / "templates"
data_dir = base_dir / "data"

# Setup Jinja2 environment
jinja_env = Environment(loader=FileSystemLoader(str(templates_dir)))

def generate_thumbnail(title: str, description: str) -> str:
    """Generate thumbnail using Gemini Flash Image Preview model."""
    try:
        # For now, use Imagen on Gemini or fallback to deterministic placeholder
        # The actual Gemini image generation would require different setup
        
        # Create a unique, deterministic identifier based on title
        #title_hash = hashlib.md5(title.encode()).hexdigest()[:8]
        global api_key
        # Use a deterministic image service for consistency
        # In production, you would replace this with actual Gemini image generation
        client = genai.Client(api_key=api_key)

        prompt = (
            f"""Create a hyper-realistic, high-energy clickbait thumbnail for a news article titled "{title}". The visual style should be directly inspired by top gaming YouTuber thumbnails, focusing on grabbing attention immediately.

        **Key Visual Elements:**

        *    Feature random memes if appropriate to be highly humorous, but not too much.
        *    Use a vibrant, oversaturated color palette with high contrast. Add dramatic rim lighting and a subtle neon glow. Any text, if present should be at the upper half of the image and should not be more than 2 words 
        *   **Style:** Minimal anime, cartoon, or hand-drawn illustration styles. The final image must be high definition."""

        )

        response = client.models.generate_content(
            model="gemini-2.5-flash-image-preview",
            contents=[prompt],
        )
        # If the API returns image data (e.g., in part.inline_data), encode it as base64 and embed as a data URL in HTML.
        import tempfile

        thumbnail_url = None  # Will hold the URL from the upload service

        for part in response.candidates[0].content.parts:
            if part.text is not None:
                print(part.text)
            elif part.inline_data is not None:
                # Get image bytes
                image_bytes = part.inline_data.data
                # Create a temporary file to save the image
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                    temp_file.write(image_bytes)
                    temp_file_path = temp_file.name
                
                try:
                    # Compress the image before uploading
                    
                    # Open and compress the image
                    with Image.open(temp_file_path) as img:
                        # Convert to RGB if necessary (for PNG with transparency)
                        if img.mode in ('RGBA', 'LA', 'P'):
                            img = img.convert('RGB')
                        
                        # Resize if too large (max 1200px width)
                        if img.width > 1200:
                            ratio = 1200 / img.width
                            new_height = int(img.height * ratio)
                            img = img.resize((1200, new_height), Image.Resampling.LANCZOS)
                        
                        # Save compressed image to bytes
                        compressed_buffer = BytesIO()
                        img.save(compressed_buffer, format='JPEG', quality=85, optimize=True)
                        compressed_data = compressed_buffer.getvalue()
                    
                    # Upload the compressed image to the service
                    files = {'image': ('image.jpg', compressed_data, 'image/jpeg')}
                    response_upload = requests.post('http://68.154.32.96:8111/api/upload', files=files)
                    
                    if response_upload.status_code == 200:
                        upload_data = response_upload.json()
                        thumbnail_url = upload_data['url']
                    else:
                        print(f"Upload failed with status code: {response_upload.status_code}")
                        thumbnail_url = "https://via.placeholder.com/800x450/0066cc/ffffff?text=AI+News"
                        
                except Exception as upload_error:
                    print(f"Error uploading image: {upload_error}")
                    thumbnail_url = "https://via.placeholder.com/800x450/0066cc/ffffff?text=AI+News"
                finally:
                    # Clean up temporary file
                    os.unlink(temp_file_path)

        # Now, thumbnail_url can be used as the src attribute in an <img> tag in HTML
        
        print(f"Generated thumbnail for: {title[:50]}...")
        return thumbnail_url
        
    except Exception as e:
        print(f"Error generating thumbnail: {e}")
        return "https://via.placeholder.com/800x450/0066cc/ffffff?text=AI+News"

def make_title_clickbait(original_title: str,content: str) -> str:
    """Use Gemini Pro to make titles more clickbait."""
    try:
        global api_key
        client = genai.Client(api_key=api_key)

        
        
        prompt = f"""
        Transform this news title into a more engaging, clickbait version:
        
        Original title: "{original_title}"
        Content: "{content}"
        Rules:

        Return only the improved title, nothing else.
        """
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=[prompt],
        )
        
        return response.candidates[0].content.parts[0].text.strip().strip('"').strip("'")
        
    except Exception as e:
        print(f"Error making title clickbait: {e}")
        return original_title

def categorize_articles(articles: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Categorize articles using Gemini."""
    try:
        client = genai.Client(api_key=api_key)
        titles_text = "\n".join([f"{i+1}. {article['title']}" for i, article in enumerate(articles)])
        
        prompt = f"""
        Analyze these AI news article titles and categorize them into logical groups.
        
        Titles:
        {titles_text}
        
        Create categories based on recurring themes like:
        - OpenAI/ChatGPT
        - Google/Gemini
        - Meta/AI Research
        - AI Agents
        - AI Tools
        - Model Context Protocol (MCP)
        - AI Developments (for general news)
        
        Return only a JSON object mapping category names to lists of article numbers (1-based).
        Example: {{"OpenAI": [1, 3], "AI Tools": [2, 4, 5]}}
        """
        
        response = client.models.generate_content(prompt)
        
        # Clean and parse response
        response_text = response.text.strip()
        if response_text.startswith('```json'):
            response_text = response_text.strip('```json').strip('```').strip()
        
        categories = json.loads(response_text)
        
        # Reorganize articles by category
        categorized = {}
        for category, article_numbers in categories.items():
            categorized[category] = []
            for num in article_numbers:
                if 1 <= num <= len(articles):
                    categorized[category].append(articles[num - 1])
        
        return categorized
        
    except Exception as e:
        print(f"Error categorizing articles: {e}")
        # Fallback: put all articles under "AI Developments"
        return {"AI Developments": articles}

def generate_quiz(contents: str) -> None:
    """Generate quiz using Gemini 2.5 Pro."""
    try:
        global api_key
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        Create a 10-question multiple choice quiz based on this AI news content.
        
        Content:
        {contents}
        
        Requirements:
        - 10 questions total
        - Each question has 4 options (A, B, C, D)
        - Questions should be mildly challenging 
        - Avoid trivial questions or questions where the answer is obvious from the question text
        - Create plausible wrong answers that could confuse someone who only skimmed the content
        - Focus on implications, connections between concepts, and nuanced details
        - Test analytical thinking, not just recall of basic facts
        - Make all options similar in length and complexity to avoid obvious answers
        - Include questions about technical details, business implications, and strategic decisions
        - Ensure wrong answers are believable and related to the topic
        - Do not include "According to the text" or "The Content" or related phrases
        Examples of BAD questions to avoid:
        - "What company released ChatGPT?" (too obvious)
        - "Is AI getting better?" (answer in question)
        - Questions with obviously wrong answers like "banana" when others are technical terms
        
        Return ONLY a valid JSON array with this exact format:
        [
            {{
                "question": "Question text here?",
                "options": {{
                    "A": "Option A text",
                    "B": "Option B text", 
                    "C": "Option C text",
                    "D": "Option D text"
                }},
                "answer": "A"
            }}
        ]
        """
        

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=[prompt],
        )
        # Clean response
        response_text = response.text.strip()
        if response_text.startswith('```json'):
            response_text = response_text.strip('```json').strip('```').strip()
        
        quiz_data = json.loads(response_text)
        
        # Save quiz to file
        quiz_path = data_dir / "quiz.json"
        data_dir.mkdir(exist_ok=True)
        
        with open(quiz_path, "w", encoding="utf-8") as f:
            json.dump(quiz_data, f, ensure_ascii=False, indent=2)
        data = json.dumps(quiz_data).replace('\n', '').replace('\r', '').encode()
        print(f"Quiz generated and saved to {quiz_path}")
        #curl -X POST -d @quiz.json -H 'Content-Type: application/json' http://127.0.0.1:8002/api/upload-quiz
        response = requests.post('https://aiquiz.shorthills.ai/api/upload-quiz', data=data, headers={'Content-Type': 'application/json'})
        if response.status_code == 200:
            print("Quiz uploaded successfully")
        else:
            print(f"Error uploading quiz: {response.status_code}")
        
    except Exception as e:
        print(f"Error generating quiz: {e}")

def load_and_process_news(json_path: Path, limit: int = 5) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Load and process news articles from JSON file."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"filtered_ai_news.json not found at {json_path}")
    except json.JSONDecodeError:
        raise ValueError("Could not decode filtered_ai_news.json")

    if "articles" not in data or not isinstance(data["articles"], list):
        raise ValueError("Invalid JSON structure - expected 'articles' array")

    # Limit to specified number of articles
    articles = data["articles"][:limit]
    processed_articles = []
    all_content = []

    for article in articles:
        title = article.get("title", "N/A")
        source_url = article.get("source_url", "N/A")
        content = article.get("content", "N/A")
        if len(content) > 300:
            content = content[:300]
            content = content + "..."
        # Make title more clickbait
        clickbait_title = make_title_clickbait(title,content)
        
        # Generate thumbnail
        thumbnail = generate_thumbnail(title, content)
        
        processed_article = {
            "title": clickbait_title,
            "original_title": title,
            "content": content,
            "source_url": source_url,
            "thumbnail": thumbnail
        }
        
        processed_articles.append(processed_article)
        all_content.append(content)

    return processed_articles, all_content

def load_trending_repos(repo_json_path: Path) -> List[Dict[str, Any]]:
    """Load trending repositories from JSON file."""
    try:
        with open(repo_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    if "repos" not in data or not isinstance(data["repos"], list):
        return []

    repos = []
    for repo_data in data["repos"]:
        repo_url = repo_data.get("repo_url", "N/A")
        
        # Generate thumbnail for repo
        repo_name = repo_data.get("repo_name", "Repository")
        #description = repo_data.get("description", "")
        #thumbnail = generate_thumbnail(f"GitHub: {repo_name}", description)
        
        repos.append({
            "repo_url": repo_url,
            "thumbnail":f"https://opengraph.githubassets.com/12e7c96052543eb3beff547811277a293e6d003a901ebf270312c9b352b4460e/{repo_name}"
        })

    return repos

def generate_email_html(articles: List[Dict[str, Any]]) -> str:
    """Generate email HTML using Jinja2 template."""
    try:
        # Categorize articles
        categorized_articles = categorize_articles(articles)
        
        # Prepare template data
        template_data = {
            "greeting": "Good morning Shorthills Geeks!",
            "titles": [article["title"] for article in articles],
            "categorized_articles": categorized_articles,
            #"trending_repos": repos,
            "quiz_url": "http://104.208.162.61:8002/"
        }
        
        # Load and render template
        template = jinja_env.get_template('email_template.j2')
        rendered_html = template.render(template_data)
        
        return rendered_html
        
    except Exception as e:
        print(f"Error generating email HTML: {e}")
        return f"<html><body><p>Error generating email: {e}</p></body></html>"

def generate_news_page_html(articles: List[Dict[str, Any]], template_name: str = 'crunch_template.j2') -> str:
    """Generate news page HTML using specified template."""
    try:
        if template_name == 'crunch_template.j2':
            # Prepare data for crunch template (1 hero + 4 secondary)
            template_data = {
                'hero_story': {
                    'title': articles[0]['title'],
                    'description': articles[0]['content'],
                    'image_url': articles[0]['thumbnail'],
                    'tag': 'BREAKING NEWS',
                    'author_name': 'AI Digest Staff',
                    'published_time': '2 hours ago'
                },
                'secondary_articles': []
            }
            
            # Add remaining articles as secondary
            for article in articles[1:]:  # Max 4 secondary articles
                template_data['secondary_articles'].append({
                    'title': article['title'],
                    'description': article['content'],
                    'image_url': article['thumbnail'],
                    'category': 'AI News',
                    'author_name': 'AI Digest Staff',
                    'published_time': 'Recently'
                })
        
        elif template_name == 'ndtv_fin.j2':
            # Prepare data for NDTV template (2 featured + 3 top stories)
            template_data = {
                'featured_stories': [
                    {
                        'title': articles[0]['title'],
                        'description': articles[0]['content'],
                        'image_url': articles[0]['thumbnail'],
                        'url': articles[0]['source_url']
                    },
                    {
                        'title': articles[1]['title'],
                        'description': articles[1]['content'], 
                        'image_url': articles[1]['thumbnail'],
                        'url': articles[1]['source_url']
                    }
                ],
                'top_stories': []
            }
            
            # Add remaining as top stories
            for article in articles[2:]:  # Max 3 top stories
                template_data['top_stories'].append({
                    'title': article['title'],
                    'description': article['content'],
                    'image_url': article['thumbnail'],
                    'url': article['source_url']
                })
            template_data['date'] = datetime.now().strftime("%Y-%m-%d")
        # Load and render template
        template = jinja_env.get_template(template_name)
        rendered_html = template.render(template_data)
        
        return rendered_html
        
    except Exception as e:
        print(f"Error generating news page HTML: {e}")
        return f"<html><body><p>Error generating news page: {e}</p></body></html>"

def main():
    """Main function to generate AI news content."""
    # Get command line arguments
    if len(sys.argv) < 2:
        print("Usage: python ai_news_generator.py <filtered_ai_news.json> [trending_repos.json]")
        sys.exit(1)
    
    news_json_path = Path(sys.argv[1])
    repo_json_path = Path(sys.argv[2]) if len(sys.argv) > 2 else base_dir / "trending_repos.json"
    
    # Check if files exist
    if not news_json_path.exists():
        print(f"Error: News file not found at {news_json_path}")
        sys.exit(1)
    
    try:
        print("Loading and processing news articles...")
        articles, contents = load_and_process_news(news_json_path, limit=5)
        
        print("Loading trending repositories...")
        #repos = load_trending_repos(repo_json_path)
        
        print("Generating quiz...")
        generate_quiz("\n".join(contents))
        
        print("Generating email content...")
        #email_html = generate_email_html(articles)
        
        print("Generating news pages...")
        #crunch_html = generate_news_page_html(articles, 'crunch_template.j2')
        ndtv_html = generate_news_page_html(articles, 'ndtv_fin.j2')
        
        # Save outputs
        output_dir = base_dir / "output3"
        output_dir.mkdir(exist_ok=True)
        
        # Save email
        #with open(output_dir / "email.html", 'w', encoding='utf-8') as f:
        #    f.write(email_html)
        
        # Save news pages
        #with open(output_dir / "crunch_news.html", 'w', encoding='utf-8') as f:
        #    f.write(crunch_html)
            
        with open(output_dir / "ndtv_news.html", 'w', encoding='utf-8') as f:
            f.write(ndtv_html)
        
        # Generate email message JSON for API
        #recipients = os.getenv('AI_NEWS_RECIPIENTS')
        #if recipients:
        #    recipients_data = json.loads(recipients)["toRecipients"]
            """
            email_message = {
                "message": {
                    "isReadReceiptRequested": True,
                    "subject": "Daily AI News",
                    "body": {
                        "contentType": "HTML",
                        "content": email_html
                    },
                    "toRecipients": recipients_data
                }
            }
            
            with open(output_dir / "email_message.json", 'w', encoding='utf-8') as f:
                json.dump(email_message, f, indent=2)
        """
        print(f"✅ Generated files in {output_dir}:")
        print("  - email.html (email content)")
        #print("  - crunch_news.html (crunch-style news page)")
        print("  - ndtv_news.html (ndtv-style news page)")
        print("  - email_message.json (API-ready email)")
        print(f"  - quiz.json (quiz data)")
        
    except Exception as e:
        print(f"Error in main execution: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
