import os
import sys
import time
import requests
from dotenv import load_dotenv
from openai import OpenAI

# Load API keys from .env
load_dotenv()
GAMMA_API_KEY = os.getenv("GAMMA_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not GAMMA_API_KEY:
    print("Error: Please set GAMMA_API_KEY in your .env file.")
    sys.exit(1)
if not OPENAI_API_KEY:
    print("Error: Please set OPENAI_API_KEY in your .env file.")
    sys.exit(1)

GAMMA_API_URL = "https://api.gamma.app/public-api/v0.1/generations"
client = OpenAI(api_key=OPENAI_API_KEY)

def format_and_chunk_text(text):
    """Use OpenAI to format and chunk the input text into presentation-friendly sections."""
    prompt = f"""Please format the following text into clear sections suitable for a presentation. 
    Break it down into logical chunks that would work well as slides.
    For each section, identify if it contains tables, lists, or other structured content.
    Format the output as a JSON array of objects, where each object has:
    - title: A catchy title for the section
    - content: The formatted content
    - has_table: boolean indicating if section contains tabular data
    - has_list: boolean indicating if section contains lists
    - has_code: boolean indicating if section contains code

    Text to format:
    {text}"""

    response = client.chat.completions.create(
        model="gpt-4-turbo-preview",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that formats text into presentation-friendly sections."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )
    
    return response.choices[0].message.content

def poll_generation_status(gen_id):
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": GAMMA_API_KEY
    }
    status_url = f"{GAMMA_API_URL}/{gen_id}"
    for _ in range(60):  # Poll for up to 5 minutes
        resp = requests.get(status_url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "completed":
                print("Gamma doc link:", data.get("docUrl"))
                print("Download link:", data.get("downloadUrl"))
                return
            elif data.get("status") == "failed":
                print("Error: Generation failed.")
                sys.exit(1)
        time.sleep(5)
    print("Error: Timed out waiting for presentation to be generated.")
    sys.exit(1)

def generate_presentation(
    prompt,
    tone="informative and somewhat humorous",
    audience="tech enthusiasts",
    text_amount="medium",
    text_mode="generate",  # Changed back to generate as it's a valid value
    num_cards=20,
    image_model="ideogram-v3",
    image_style="photorealistic",
    editor_mode="freeform",
    additional_instructions="Make the title on each slide catchy",
    theme_name="chisel",
    workspace_access="comment",
    external_access="no_access",
    skip_image_generation=False
):
    # First format and chunk the text using OpenAI
    formatted_text = format_and_chunk_text(prompt)
    
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": GAMMA_API_KEY
    }
    payload = {
        "inputText": formatted_text,
        "tone": tone,
        "audience": audience,
        "textAmount": text_amount,
        "textMode": text_mode,
        "numCards": num_cards,
        "imageModel": image_model,
        "imageStyle": image_style,
        "editorMode": editor_mode,
        "additionalInstructions": additional_instructions,
        "themeName": theme_name,
        "workspaceAccess": workspace_access,
        "externalAccess": external_access,
        "skipImageGeneration": skip_image_generation
    }
    response = requests.post(GAMMA_API_URL, json=payload, headers=headers)
    if response.status_code in (200, 201):
        data = response.json()
        gen_id = data.get("id")
        if not gen_id:
            print("Error: No generation ID returned.")
            sys.exit(1)
        print(f"Generation started. Polling for completion (id: {gen_id})...")
        poll_generation_status(gen_id)
    else:
        print("Error:", response.status_code, response.text)
        sys.exit(1)

if __name__ == "__main__":
    # Read prompt from stdin
    prompt = sys.stdin.read().strip()
    if not prompt:
        print("Error: No prompt provided via stdin.")
        sys.exit(1)
    generate_presentation(prompt)