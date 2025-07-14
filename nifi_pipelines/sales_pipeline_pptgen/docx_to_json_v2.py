import json
import re
import os
from openai import AzureOpenAI
from typing import Dict, Any, List
from dotenv import load_dotenv
from docx import Document
import argparse
import logging
from collections import defaultdict
import sys

# Configure logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

load_dotenv()

class DocumentInfoExtractor:
    def __init__(self, azure_endpoint: str, api_key: str, api_version: str = "2024-12-01-preview"):
        """
        Initialize Azure OpenAI client
        
        Args:
            azure_endpoint: Azure OpenAI endpoint URL
            api_key: Azure OpenAI API key
            api_version: API version (default: 2024-12-01-preview)
        """
        self.client = AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=api_key,
            api_version=api_version
        )
    
    def extract_document_info(self, text: str, deployment_name: str = "gpt-4o-mini") -> Dict[str, Any]:
        """
        Extract slide numbers, source files, and links from DOCX text using Azure OpenAI
        
        Args:
            text: Input text from DOCX file
            deployment_name: Azure OpenAI deployment name
            
        Returns:
            Dictionary containing extracted information grouped by document
        """
        # System prompt for structured extraction
        system_prompt = """
        You are an expert document information extractor. Your job is to analyze the provided text and extract structured information for each relevant item.
        For each line or section, extract the following fields if present:
        - slide_number: The slide number (as an integer), if the line contains [Slide X] or Slide X.
        - source_file: The filename after 'Source File:' (e.g., MCAP.docx, BuyProperly.pptx, ShAI_Walmart ASR.docx).
        - link: The URL after 'LINK[' or 'LINK [' or similar patterns (ensure you capture the full URL).
        - content_summary: A concise summary (max 200 characters) of the main content or topic of the line/section.
        - line_number: The line number in the input text (starting from 1).
        
        Return a JSON object with this structure:
        {
          "raw_items": [
            {
              "slide_number": <integer or null>,
              "source_file": "<filename or null>",
              "link": "<url or null>",
              "content_summary": "<summary>",
              "line_number": <integer>
            }
          ]
        }
        
        Guidelines:
        - If a field is not present in a line, set its value to null.
        - Only include lines/sections that have at least one of: slide_number, source_file, or link.
        - Extract ALL slide numbers, source files, and links you find.
        - Do not include any text outside the JSON object in your response.
        """
        
        user_prompt = f"""
        Analyze the following DOCX text and extract the required information:
        
        {text}
        
        Identify:
        - Slide references (e.g., [Slide 11], Slide 13, etc.)
        - Source file references (e.g., **Source File:** BuyProperly.pptx)
        - Links/URLs (e.g., LINK [https://...] or similar patterns)
        - Main topics or content themes
        """
        
        try:
            response = self.client.chat.completions.create(
                model=deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,  # Low temperature for consistent extraction
                max_tokens=4000
            )
            
            extracted_content = response.choices[0].message.content
            # Remove Markdown code block markers if present
            cleaned_content = re.sub(r"^```(?:json)?\s*|```$", "", extracted_content.strip(), flags=re.MULTILINE)
            
            try:
                raw_result = json.loads(cleaned_content)
            except json.JSONDecodeError as e:
                # Try to extract the JSON block if still not valid
                match = re.search(r"\{[\s\S]*\}", cleaned_content)
                if match:
                    json_block = match.group(0)
                    try:
                        raw_result = json.loads(json_block)
                    except Exception as e2:
                        logger.error(f"JSON decode error after extracting block: {e2}\nCleaned content was: {json_block}")
                        raise ValueError("LLM did not return valid JSON after cleaning. See logs for details.")
                else:
                    logger.error(f"JSON decode error: {e}\nLLM output was: {extracted_content}\nCleaned content was: {cleaned_content}")
                    raise ValueError("LLM did not return valid JSON. See logs for details.")
            
            # Process the raw items to group by document
            return self._group_by_document(raw_result.get('raw_items', []))
            
        except Exception as e:
            logger.error(f"Azure OpenAI extraction error: {e}")
            raise
    
    def _group_by_document(self, raw_items: List[Dict]) -> Dict[str, Any]:
        """
        Group extracted items by source file and aggregate slide numbers
        
        Args:
            raw_items: List of raw extracted items
            
        Returns:
            Dictionary with grouped items
        """
        # Group items by source file
        doc_groups = defaultdict(lambda: {
            'slide_numbers': [],
            'links': set(),
            'content_summaries': [],
            'line_numbers': []
        })
        
        # Process each raw item
        for item in raw_items:
            source_file = item.get('source_file')
            slide_number = item.get('slide_number')
            link = item.get('link')
            content_summary = item.get('content_summary', '')
            line_number = item.get('line_number')
            
            # Create a key for grouping (use source_file if available, otherwise use link or a generic key)
            if source_file:
                key = source_file
            elif link:
                # Extract filename from link if possible
                key = self._extract_filename_from_link(link)
            else:
                key = f"unknown_document_{line_number}"
            
            # Add slide number if present
            if slide_number and slide_number not in doc_groups[key]['slide_numbers']:
                doc_groups[key]['slide_numbers'].append(slide_number)
            
            # Add link if present
            if link:
                doc_groups[key]['links'].add(link)
            
            # Add content summary if present
            if content_summary and content_summary not in doc_groups[key]['content_summaries']:
                doc_groups[key]['content_summaries'].append(content_summary)
            
            # Add line number
            if line_number:
                doc_groups[key]['line_numbers'].append(line_number)
        
        # Convert to the desired output format
        extracted_items = []
        for doc_name, doc_data in doc_groups.items():
            # Sort slide numbers
            slide_numbers = sorted(doc_data['slide_numbers']) if doc_data['slide_numbers'] else []
            
            # Get the first link (assuming one link per document)
            link = list(doc_data['links'])[0] if doc_data['links'] else None
            
            # Combine content summaries
            content_summary = '; '.join(doc_data['content_summaries'][:3])  # Limit to first 3 summaries
            if len(content_summary) > 200:
                content_summary = content_summary[:197] + "..."
            
            # Get line numbers (first occurrence)
            line_number = min(doc_data['line_numbers']) if doc_data['line_numbers'] else None
            
            extracted_items.append({
                "slide_number": slide_numbers if slide_numbers else [],
                "source_file": doc_name if doc_name and not doc_name.startswith('unknown_document_') else None,
                "link": link,
                "content_summary": content_summary,
                "line_number": line_number
            })
        
        return {
            "extracted_items": extracted_items,
            "total_items": len(extracted_items)
        }
    
    def _extract_filename_from_link(self, link: str) -> str:
        """
        Extract filename from SharePoint link or return a generic name
        """
        if not link:
            return "unknown_document"
        
        # Try to extract filename from SharePoint link
        match = re.search(r'file=([^&]+)', link)
        if match:
            filename = match.group(1)
            # URL decode common characters
            filename = filename.replace('%20', ' ').replace('%26', '&')
            return filename
        
        # Fallback to extracting from URL path
        try:
            from urllib.parse import urlparse
            parsed = urlparse(link)
            if parsed.path:
                return os.path.basename(parsed.path)
        except:
            pass
        
        return "unknown_document"

def extract_text_from_docx(docx_path: str) -> str:
    """Extract all text from a DOCX file as a single string."""
    try:
        doc = Document(docx_path)
        return '\n'.join(para.text for para in doc.paragraphs if para.text.strip())
    except Exception as e:
        logger.error(f"Error reading DOCX file {docx_path}: {e}")
        raise

if __name__ == "__main__":
    try:
        # Read JSON input from stdin (NiFi FlowFile)
        input_data = sys.stdin.read()
        if not input_data.strip():
            raise ValueError("No JSON data received from stdin.")

        # Parse JSON
        json_data = json.loads(input_data)

        # Load credentials
        AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
        API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
        DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

        if not AZURE_ENDPOINT or not API_KEY:
            raise ValueError("Azure OpenAI credentials not set in environment variables.")

        # Convert JSON to string for LLM processing
        json_content = json.dumps(json_data, indent=2)

        # Run extraction
        extractor = DocumentInfoExtractor(AZURE_ENDPOINT, API_KEY)
        result = extractor.extract_document_info(json_content, DEPLOYMENT_NAME)

        # Post-process to group by source_file and link
        extracted_items = result.get('extracted_items', [])
        grouped_output = extractor._group_by_document(extracted_items)

        # Write output JSON to stdout (for NiFi)
        sys.stdout.write(json.dumps(grouped_output, indent=2, ensure_ascii=False))

    except Exception as e:
        logger.error(f"NiFi processing error: {e}")
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)