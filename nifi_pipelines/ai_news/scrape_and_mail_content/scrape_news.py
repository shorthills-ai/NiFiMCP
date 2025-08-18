import requests
from bs4 import BeautifulSoup, NavigableString
from urllib.parse import urljoin
import json
import re

BASE_URL = "https://news.smol.ai/"

# --- 1. Define Sections to Scrape (using their HTML IDs) ---
# We will only process content under headings with these IDs.
SECTIONS_TO_INCLUDE = {
    'ai-twitter-recap': "AI Twitter Recap",
    'rlocalllama--rlocalllm-recap': "/r/LocalLlama + /r/localLLM Recap",
    'discord-high-level-discord-summaries': "Discord: High level Discord summaries"
}

# Define section headers to STOP processing at, to exclude sub-topics.
SECTIONS_TO_EXCLUDE = [
    'less-technical-ai-subreddit-recap',
    'discord-detailed-by-channel-summaries-and-links'
]


def get_latest_issue_url():
    """Finds the URL for the most recent news issue on the homepage."""
    print(f"Fetching homepage: {BASE_URL}...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(BASE_URL, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        timeline_list = soup.find('ul', id='timeline')
        if not timeline_list:
            print("Error: Could not find the timeline list.")
            return None
            
        latest_issue_link = timeline_list.find('a', href=True)
        if latest_issue_link:
            full_url = urljoin(BASE_URL, latest_issue_link['href'])
            print(f"Found latest issue URL: {full_url}")
            return full_url
        else:
            print("Error: Could not find a link within the timeline.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching homepage: {e}")
        return None

def parse_issue_page(html_content, issue_url):
    """
    Parses the HTML of a specific issue page, extracting and filtering news.
    The source_url will be a direct link to the section on the page.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    articles = []

    # --- 1. Scrape the Main Headline and Introduction ---
    main_h1 = soup.find('h1', class_='text-3xl')
    if main_h1:
        page_title = ' '.join(main_h1.get_text(strip=True).split())
        intro_content = []
        article_div = soup.find('div', class_='astro-entry')
        
        if article_div:
            # The intro paragraphs are before the first <h1> section header
            for elem in article_div.find('p').find_next_siblings():
                if elem.name == 'h1': # Stop at the first main section
                    break
                if elem.name == 'p':
                    intro_content.append(elem.get_text(strip=True))
            
            full_intro_content = ' '.join(intro_content)
            
            # The source URL points to the main content area of the page
            articles.append({
                "title": page_title,
                "content": full_intro_content,
                "source_url": f"{issue_url}#main-content"
            })

    # --- 2. Scrape Content from Specific Sections ---
    # Find all headings that could be section starts
    all_headings = soup.find_all(['h1', 'h2', 'h3'])
    
    for heading in all_headings:
        heading_id = heading.get('id', '')

        if heading_id not in SECTIONS_TO_INCLUDE:
            continue
            
        # *** CHANGE: Construct the full URL for the section anchor ***
        section_url = f"{issue_url}#{heading_id}"
        print(f"Processing section: {section_url}")

        # Find all bullet points (li) under this section until the next excluded heading
        for sibling in heading.find_next_siblings():
            if sibling.name in ['h1', 'h2'] and sibling.get('id', '') in SECTIONS_TO_EXCLUDE:
                break
            
            if sibling.name == 'ul':
                for li in sibling.find_all('li', recursive=False):
                    strong_tag = li.find('strong')
                    
                    if strong_tag:
                        title = strong_tag.get_text(strip=True).strip(":")
                        strong_tag.extract()
                        content = li.get_text(strip=True)
                        
                        if title and content:
                             articles.append({
                                "title": title,
                                "content": content,
                                "source_url": section_url # Use the constructed URL
                            })
                break # Process only the first list after the heading

    return articles

if __name__ == "__main__":
    latest_issue_url = get_latest_issue_url()
    
    if latest_issue_url:
        print(f"\nFetching content from latest issue: {latest_issue_url}")
        try:
            response = requests.get(latest_issue_url, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            
            # The main parsing logic is now in parse_issue_page
            articles_list = parse_issue_page(response.text, latest_issue_url)
            
            if articles_list:
                final_output = {"articles": articles_list}
                
                output_filename = 'ai_news.json'
                with open(output_filename, 'w', encoding='utf-8') as f:
                    json.dump(final_output, f, ensure_ascii=False, indent=2)
                    
                print(f"\n✅ Success! Scraped {len(articles_list)} articles.")
                print(f"Results saved to '{output_filename}'")
            else:
                print("\nNo relevant news found based on the specified sections.")

        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch the issue page content: {e}")