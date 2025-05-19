import asyncio
import os
import json
import re
import subprocess
import sys
from pydantic import BaseModel
from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent
from dotenv import load_dotenv
from asyncio import TimeoutError

# Load environment variables
load_dotenv()

# Constants
INPUT_FOLDER = 'jsons_to_scrape'
OUTPUT_FOLDER = 'scraped_outputs'
TIMEOUT_SECONDS = 60.0

# Ensure output directory exists
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def install_dependencies():
    """Install system dependencies for headless browser on Linux."""
    if not sys.platform.startswith('linux'):
        return

    try:
        print("Installing system dependencies for headless browser...")
        subprocess.run(['sudo', 'apt-get', 'update'], check=True)
        subprocess.run(['sudo', 'apt-get', 'install', '-y', 
                        'libnss3', 'libnspr4', 'libatk1.0-0', 'libatk-bridge2.0-0', 'libcups2',
                        'libdrm2', 'libxkbcommon0', 'libxcomposite1', 'libxdamage1', 'libxfixes3',
                        'libxrandr2', 'libgbm1', 'libasound2', 'libpango-1.0-0', 'libcairo2'], check=True)
        subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'], check=True)
        subprocess.run([sys.executable, '-m', 'playwright', 'install-deps'], check=True)
        print("✅ Dependencies installed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error installing dependencies: {e}")
        sys.exit(1)

class UsedResult(BaseModel):
    data: dict

llm = ChatGoogleGenerativeAI(model='gemini-2.0-flash-exp')

async def process_json_folder(folder_path: str, output_path: str):
    json_files = [f for f in os.listdir(folder_path) if f.endswith('.json')]

    for idx, file_name in enumerate(json_files):
        file_path = os.path.join(folder_path, file_name)

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            items = data.get("catalog_url", {}).get("items", [])
            if not isinstance(items, list) or not items:
                raise ValueError("Missing or invalid 'items' list")

            url = next((item.get("link") for item in items if "link" in item), None)
            if not url:
                raise ValueError("No valid 'link' found in items list")
        except Exception as e:
            print(f"[{idx+1}/{len(json_files)}] ❌ Error loading {file_name}: {e}")
            continue

        prompt = f"""You are given the website URL: {url}
This page consists of details about an automobile or related product's part. Find the section with product details like description or specifications. If the URL ends with '.pdf', skip it.
Your final output should be a JSON object with:
- data: JSON object containing part details.
IMPORTANT: Return ONLY the raw JSON. No comments, labels, or markdown.
"""

        agent = Agent(task=prompt, llm=llm)

        try:
            history = await asyncio.wait_for(agent.run(), timeout=TIMEOUT_SECONDS)
        except TimeoutError:
            print(f"[{idx+1}/{len(json_files)}] ⏱️ Timeout processing {file_name}")
            continue
        except Exception as e:
            print(f"[{idx+1}/{len(json_files)}] ❌ Error processing {file_name}: {e}")
            continue

        extracted_contents = history.extracted_content()
        result_json = extracted_contents[-2] if len(extracted_contents) >= 2 else None

        if not result_json:
            print(f"[{idx+1}/{len(json_files)}] → NO RESULT for {file_name}")
            continue

        try:
            # Remove unnecessary text, formatting, or code blocks
            cleaned_json = re.sub(r'📄\s+Extracted from page\s*:?\s*', '', result_json)
            cleaned_json = re.sub(r'```json|```', '', cleaned_json).strip()

            output_file = os.path.join(OUTPUT_FOLDER, f"{file_name}_output.json")
            with open(output_file, "w", encoding='utf-8') as f:
                f.write(cleaned_json)
        except Exception as parse_err:
            print(f"[{idx+1}/{len(json_files)}] ❌ Parsing error in {file_name}: {parse_err}")

    print(f"\n✅ Scraping complete. Output saved to '{output_path}'.")

if __name__ == '__main__':
    install_dependencies()
    asyncio.run(process_json_folder(INPUT_FOLDER, OUTPUT_FOLDER))
