


import json
import re
import os
import sys
from openai import AzureOpenAI
from typing import Dict, Any
from dotenv import load_dotenv
from docx import Document
import logging
from io import BytesIO

# Configure logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

load_dotenv()

class DocumentInfoExtractor:
    def __init__(self, azure_endpoint: str, api_key: str, api_version: str = "2024-12-01-preview"):
        self.client = AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=api_key,
            api_version=api_version
        )

    def extract_document_info(self, text: str, deployment_name: str = "gpt-4o-mini") -> Dict[str, Any]:
        system_prompt = """
        You are an expert document information extractor. Your job is to analyze the provided text and extract structured information for each relevant item.
        For each line or section, extract the following fields if present:
        - slide_number: The slide number (as an integer), if the line contains [Slide X] or Slide X.
        - source_file: The filename after 'Source File:'
        - link: The URL after 'LINK[' or 'LINK ['
        - content_summary: A concise summary (max 200 characters)
        - line_number: The line number in the input text (starting from 1).
        Only include lines that have at least one of: slide_number, source_file, or link.
        Return only a valid JSON object, nothing else.
        """

        user_prompt = f"""
        Analyze the following DOCX text and extract the required information:

        {text}
        """

        try:
            response = self.client.chat.completions.create(
                model=deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )

            extracted_content = response.choices[0].message.content
            cleaned_content = re.sub(r"^```(?:json)?\s*|```$", "", extracted_content.strip(), flags=re.MULTILINE)

            try:
                result = json.loads(cleaned_content)
                return result
            except json.JSONDecodeError:
                match = re.search(r"\{[\s\S]*\}", cleaned_content)
                if match:
                    return json.loads(match.group(0))
                raise ValueError("Failed to extract valid JSON.")
        except Exception as e:
            logger.error(f"Azure OpenAI extraction error: {e}")
            raise

def extract_text_from_docx_bytes(docx_bytes: bytes) -> str:
    """Extract all text from DOCX bytes input."""
    try:
        doc = Document(BytesIO(docx_bytes))
        return '\n'.join(para.text for para in doc.paragraphs if para.text.strip())
    except Exception as e:
        logger.error(f"Error reading DOCX content: {e}")
        raise

def main():
    try:
        # Read DOCX file from stdin (NiFi FlowFile input stream)
        docx_data = sys.stdin.buffer.read()
        if not docx_data:
            raise ValueError("No DOCX data received from stdin.")

        # Extract text from DOCX bytes
        text = extract_text_from_docx_bytes(docx_data)

        # Load credentials
        AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
        API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
        DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

        if not AZURE_ENDPOINT or not API_KEY:
            raise ValueError("Azure OpenAI credentials not set in environment variables.")

        # Initialize extractor
        extractor = DocumentInfoExtractor(azure_endpoint=AZURE_ENDPOINT, api_key=API_KEY)

        # Perform extraction
        result = extractor.extract_document_info(text, deployment_name=DEPLOYMENT_NAME)

        # Write JSON to stdout (so NiFi captures it as FlowFile content)
        sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False))

    except Exception as e:
        logger.error(f"Main processing error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()


