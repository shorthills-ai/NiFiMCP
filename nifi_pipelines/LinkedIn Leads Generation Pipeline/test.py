#!/usr/bin/env python3
import json
import pandas as pd
import os
import requests
import sys
from io import BytesIO
 
# Path to the local Excel file
EXCEL_PATH = "leads.xlsx"
 
# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT")
 
def read_excel_file():
    try:
        if os.path.exists(EXCEL_PATH):
            print(f"Excel file exists at {EXCEL_PATH}. Reading existing data...", file=sys.stderr)
            df = pd.read_excel(EXCEL_PATH)
            print(f"Successfully read existing Excel file with {len(df)} rows.", file=sys.stderr)
            return df
        else:
            print(f"Excel file does not exist at {EXCEL_PATH}. A new file will be created.", file=sys.stderr)
            return pd.DataFrame()
    except Exception as e:
        print(f"Error reading Excel file: {e}", file=sys.stderr)
        print("Proceeding with an empty DataFrame.", file=sys.stderr)
        return pd.DataFrame()
 
def save_excel_file(df):
    try:
        # Ensure the directory exists (only if a directory is specified)
        excel_dir = os.path.dirname(EXCEL_PATH)
        if excel_dir and not os.path.exists(excel_dir):
            print(f"Directory {excel_dir} does not exist. Creating it now...", file=sys.stderr)
            os.makedirs(excel_dir, exist_ok=True)
            print(f"Successfully created directory: {excel_dir}", file=sys.stderr)

        # Save the Excel file
        df.to_excel(EXCEL_PATH, index=False)
        print(f"Successfully saved Excel file to: {EXCEL_PATH} with {len(df)} rows.", file=sys.stdout)
    except Exception as e:
        print(f"Error saving Excel file: {e}", file=sys.stderr)
        raise
 
def generate_summary(data):
    url = f"{AZURE_OPENAI_ENDPOINT}openai/deployments/{AZURE_OPENAI_DEPLOYMENT_NAME}/chat/completions?api-version={AZURE_OPENAI_API_VERSION}"
    
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_OPENAI_API_KEY,
    }
 
    prompt = f"""Create a brief summary based on the following LinkedIn post data:
    Author ID: {data['id']}
    Author Name: {data['firstName']} {data['lastName']}
    Headline: {data['headline']}
    Username: {data['username']}
    Profile URL: {data['url']}
    Post Text: {data['text']}
    Content Type: {data['contentType']}
    Total Reactions: {data['totalReactionCount']}
    Post URL: {data['postUrl']}
    Share URL: {data['shareUrl']}
    Posted Date: {data['postedDate']}
    
    Provide a concise 2-3 sentence summary of the post and the author's activity."""
 
    messages = [
        {
            "role": "system",
            "content": "You are a professional summarizer. Create concise summaries of LinkedIn posts and author activity based on the provided information."
        },
        {
            "role": "user",
            "content": prompt
        }
    ]
 
    data = {
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 150
    }
 
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        summary = response.json()["choices"][0]["message"]["content"].strip()
        print(f"Generated summary: {summary}", file=sys.stderr)  # Debug: Log the summary
        return summary
    except Exception as e:
        print(f"Error generating summary: {e}", file=sys.stderr)
        return "Unable to generate summary due to API error."
 
if __name__ == "__main__":
    try:
        # Read flow file content from stdin
        input_data = sys.stdin.read()
        print(f"Input data: {input_data}", file=sys.stderr)  # Debug: Log the input data
        
        # Parse JSON input
        json_data = json.loads(input_data) if input_data else {}
        
        # Check if 'data' array exists and has at least one post
        posts = json_data.get("data", [])
        if not posts:
            raise ValueError("No posts found in the input JSON data")
 
        # Extract data from the first post
        post = posts[0]
        author = post.get("author", {})
 
        data = {
            "id": str(author.get("id", "Unknown ID")),
            "firstName": author.get("firstName", "Unknown First Name"),
            "lastName": author.get("lastName", "Unknown Last Name"),
            "headline": author.get("headline", "No headline available"),
            "username": author.get("username", "Not available"),
            "url": author.get("url", "Not available"),
            "text": post.get("text", "No post text available"),
            "contentType": post.get("contentType", "Unknown content type"),
            "totalReactionCount": str(post.get("totalReactionCount", 0)),
            "postUrl": post.get("postUrl", "Not available"),
            "shareUrl": post.get("shareUrl", "Not available"),
            "postedDate": post.get("postedDate", "Unknown date")
        }
 
        # Debug: Log the extracted data
        print(f"Extracted data: {data}", file=sys.stderr)
 
        # Generate summary
        data["summary"] = generate_summary(data)
 
        # Define column order
        columns = [
            "id",
            "firstName",
            "lastName",
            "headline",
            "username",
            "url",
            "text",
            "contentType",
            "totalReactionCount",
            "postUrl",
            "shareUrl",
            "postedDate",
            "summary"
        ]
 
        # Convert to DataFrame
        new_row_df = pd.DataFrame([data], columns=columns)
 
        # Read existing Excel file
        existing_df = read_excel_file()
 
        # Append new row
        if not existing_df.empty:
            print(f"Appending new row to existing Excel file with {len(existing_df)} rows.", file=sys.stderr)
            existing_df = existing_df.reindex(columns=columns)
            updated_df = pd.concat([existing_df, new_row_df], ignore_index=True)
        else:
            print("No existing data found. Creating new Excel file with the new row.", file=sys.stderr)
            updated_df = new_row_df
 
        # Save updated DataFrame
        save_excel_file(updated_df)
 
        # Write success message to stdout
        print("Success", file=sys.stdout)
        sys.exit(0)
 
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
