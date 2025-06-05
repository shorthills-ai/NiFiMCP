import csv
import os
from datetime import datetime
from openai import AzureOpenAI
API_key = os.getenv("api_key")
api_version= os.getenv("api_version")
azure_endpoint= os.getenv("azure_endpoint")
deployment_name= os.getenv("deployment_name")
def summarize_text(text, client, deployment_name):
    """Send text to Azure OpenAI for summarization and follow-up determination"""
    try:
        print("Sending text to Azure OpenAI for summarization...")
        response = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes email content concisely and determines if a follow-up meeting is required."},
                {"role": "user", "content": f"Please summarize this email in 1-2 sentences and then answer 'Yes' if a follow-up meeting is clearly required, or 'No' if not:\n\n{text}\n\nAnswer format: Summary: [your summary]. Follow-up required: [Yes/No]"}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error summarizing text: {e}")
        return "Summary unavailable. Follow-up required: No"

def load_existing_entries(output_file):
    """Load existing rows from output file to avoid duplicates"""
    entries = set()
    if os.path.exists(output_file):
        with open(output_file, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (row.get('email', '').strip(), row.get('subject', '').strip(), row.get('body', '').strip())
                entries.add(key)
    return entries

def process_csv(input_file, output_file, azure_config):
    print("Initializing Azure OpenAI client...")
    client = AzureOpenAI(
        api_key=azure_config['api_key'],
        api_version=azure_config['api_version'],
        azure_endpoint=azure_config['azure_endpoint']
    )

    print("Loading existing entries (if any)...")
    existing_data = []
    existing_entries = load_existing_entries(output_file)
    print(f"Found {len(existing_entries)} existing unique entries.")

    fieldnames = None
    if os.path.exists(output_file):
        with open(output_file, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            existing_data = list(reader)

    new_rows = []
    processed = 0
    skipped = 0

    print("Reading input CSV...")
    with open(input_file, mode='r', newline='', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        if not fieldnames:
            fieldnames = reader.fieldnames + ['summary', 'follow_up_required', 'invite_send']

        for row in reader:
            key = (row.get('sender_email', '').strip(), row.get('subject', '').strip(), row.get('body', '').strip())
            if key in existing_entries:
                skipped += 1
                continue  # Already summarized

            print(f"Processing new email from: {row.get('sender_email', 'unknown')}")
            if row.get('type', '').lower() == 'email' and 'body' in row:
                full_response = summarize_text(row['body'], client, azure_config['deployment_name'])
                summary = full_response.split("Follow-up required:")[0].replace("Summary:", "").strip()
                follow_up = "Yes" if "Follow-up required: Yes" in full_response else "No"
                row['summary'] = summary
                row['follow_up_required'] = follow_up
            else:
                row['summary'] = ''
                row['follow_up_required'] = 'No'

            row['invite_send'] = 'no'
            new_rows.append(row)
            processed += 1

    print(f"✅ Processed {processed} new entries. Skipped {skipped} duplicates.")
    all_rows = existing_data + new_rows

    def get_datetime(row):
        try:
            return datetime.strptime(row.get('receivedatetime', ''), '%Y-%m-%d %H:%M:%S')
        except:
            return datetime.min  # Default for bad/missing dates

    print("Sorting rows by receivedatetime...")
    all_rows.sort(key=get_datetime)

    print("Writing output to file...")
    with open(output_file, mode='w', newline='', encoding='utf-8') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"🎉 Processing complete. Output saved to {output_file}")

if __name__ == "__main__":
    azure_config = {
        'api_key': API_key,
        'api_version': api_version,
        'azure_endpoint': azure_endpoint,
        'deployment_name': deployment_name
    }

    input_csv = "/home/nifi/nifi2/users/priyanshu/Output/output.csv"
    output_csv = "/home/nifi/nifi2/users/priyanshu/Output/Sumarize.csv"

    process_csv(input_csv, output_csv, azure_config)