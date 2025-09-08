import requests
import json
import sys
import time
import csv
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

# --- Logging Setup ---
LOG_PATH = "/home/nifi/nifi2/users/cherav/GitHub_PR_Review_Bot/token_review.log"
logger = logging.getLogger("TokenLogger")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(LOG_PATH, maxBytes=5_000_000, backupCount=2)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

# --- Constants ---
api_key = ""
model_name = "gemini-2.5-pro-preview-05-06"
INPUT_TOKEN_COST = 1.25 / 1_000_000
OUTPUT_TOKEN_COST = 10.0 / 1_000_000
CSV_PATH = "/home/nifi/nifi2/users/cherav/GitHub_PR_Review_Bot/token_logs.csv"

# --- Review Generation Function ---
def gen_review(text, pr_url):
    user_prompt = (
        f"Here is the GitHub pull request diff:\n\n{text}\n\n"
        "You are an expert code reviewer. Based on the above diff, provide a detailed and structured review with the following format:\n\n"
        "1. **Categorized Issues**: Group findings under these categories:\n"
        "   - **Unoptimized Code**: Code that causes inefficiency, unnecessary processing, redundant logic, or could be optimized for performance.\n"
        "   - **Incorrect Logic**: Code that is functionally wrong, contradictory, causes runtime errors, or does not handle expected input.\n"
        "   - **Version Conflicts**: Incompatible library versions, deprecated functions, or mismatched environments.\n"
        "   - **Missing Best Practices**: Violations of style guides (e.g., PEP8), missing comments, improper naming, poor modularity, etc.\n"
        "   - **Security/Performance Issues**: Insecure data handling, missing validations, memory bottlenecks, I/O blocking, etc.\n\n"
        "2. **Line-Specific Comments**: For each issue, specify the **file name** and **line number**.\n"
        "3. **Code Snippets**: Include relevant code snippets from the diff.\n"
        "4. **Problem Explanation**: Clearly describe why this code is problematic.\n"
        "5. **Fix or Suggestion**: Propose a clear, actionable fix.\n"
        "6. **Output Format**: Present all findings as a well-formatted GitHub comment.\n\n"
        "Avoid generic summaries. Only mention technical issues from the diff with proper categorization. Avoid putting style/readability issues under 'Unoptimized Code'.\n\n"
        "IMPORTANT: Do NOT wrap your entire response in markdown code blocks (markdown). Start directly with the content."
    )

    system_instruction = (
        "You are a senior software engineer who reviews GitHub pull requests. "
        "Your task is to analyze the code diff provided and generate clear, concise, "
        "and actionable review comments. Follow internal engineering best practices and coding standards."
    )

    combined_prompt = f"{system_instruction}\n\n{user_prompt}"
    payload = {
        "contents": [{
            "role": "user",
            "parts": [{"text": combined_prompt}]
        }],
        "generationConfig": {"temperature": 0.2}
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}

    start_time = time.time()
    response = requests.post(url, headers=headers, json=payload)
    end_time = time.time()
    duration = round(end_time - start_time, 3)

    logger.info(f"Request duration: {duration}s")
    logger.info(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        try:
            gemini_response = response.json()
            parts = gemini_response["candidates"][0]["content"]["parts"]
            ai_reply = parts[0].get("text", "No content")

            usage = gemini_response.get("usageMetadata", {})
            input_tokens = usage.get("promptTokenCount", 0)
            output_tokens = usage.get("candidatesTokenCount", 0)
            cost = round(input_tokens * INPUT_TOKEN_COST + output_tokens * OUTPUT_TOKEN_COST, 6)

            logger.info(f"Tokens - input: {input_tokens}, output: {output_tokens}, cost: ${cost}")

            write_to_csv(pr_url, input_tokens, output_tokens, duration, cost)

            wrapped_output = {
                "choices": [{
                    "message": {
                        "content": ai_reply
                    }
                }]
            }

            logger.info("Review successfully generated.")
            print(json.dumps(wrapped_output, indent=2))
            return wrapped_output
        except Exception as e:
            logger.exception("Failed to parse Gemini response.")
            print(json.dumps({"error": str(e)}))
    else:
        logger.error(f"API Error: {response.text}")
        print(json.dumps({"error": response.text}))

# --- CSV Logging ---
def write_to_csv(pr_url, input_tokens, output_tokens, duration, cost):
    file_exists = os.path.isfile(CSV_PATH)
    try:
        with open(CSV_PATH, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            if not file_exists:
                writer.writerow(["Timestamp", "PR_Link", "InputTokens", "OutputTokens", "Latency_sec", "Cost_USD"])
            writer.writerow([datetime.utcnow().isoformat(), pr_url, input_tokens, output_tokens, duration, cost])
        logger.info("Token log written to CSV.")
    except Exception as e:
        logger.exception("Failed to write CSV.")

# --- Main Entrypoint ---
def main():
    try:
        if len(sys.argv) < 2:
            raise ValueError("Missing PR link. Usage: python3 script.py <pr_link>")

        pr_url = sys.argv[1]
        logger.info(f"PR URL: {pr_url}")
        logger.info(f"sys.argv: {sys.argv}")

        input_text = sys.stdin.read().strip()
        logger.info(f"Diff length: {len(input_text)} chars")

        diff_content = f'"""{input_text}"""'
        gen_review(diff_content, pr_url)

    except Exception as e:
        logger.exception("Unexpected error in main.")
        print(json.dumps({"error": str(e)}))

# --- Run ---
if __name__ == "__main__":
    main()
