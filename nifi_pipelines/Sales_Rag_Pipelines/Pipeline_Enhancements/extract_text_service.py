


import os
import sys
import json
import logging
from io import BytesIO
from typing import List, Dict, Any
from pptx import Presentation
from docx import Document
from dotenv import load_dotenv
import numpy as np
from azure.storage.blob import BlobServiceClient, BlobClient, ContentSettings
import re
import subprocess
import uuid
import hashlib
import zipfile
import tempfile

# Load environment variables
load_dotenv()

# === Configuration ===
AZURE_ACCOUNT_URL = os.environ["AZURE_BLOB_ACCOUNT_URL"]
AZURE_CONTAINER_NAME = os.environ.get("AZURE_CONTAINER_NAME", "ppt-slide-storage")
AZURE_SAS_TOKEN = os.environ["AZURE_SAS_TOKEN"]

# === Logging ===
# Configure logging to write to stderr only (not stdout) to avoid contaminating JSON output
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr  # Force logs to stderr
)
logger = logging.getLogger(__name__)

# Create service and container clients
blob_service_client = BlobServiceClient(account_url=AZURE_ACCOUNT_URL, credential=AZURE_SAS_TOKEN)

def get_blob_client(blob_name: str) -> BlobClient:
    container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)
    return container_client.get_blob_client(blob_name)

def blob_exists(blob_name: str) -> bool:
    blob_client = get_blob_client(blob_name)
    try:
        blob_client.get_blob_properties()
        return True
    except Exception:
        return False

def download_json_from_blob(blob_name: str) -> dict:
    blob_client = get_blob_client(blob_name)
    stream = blob_client.download_blob()
    return json.loads(stream.readall())

def upload_json_to_blob(blob_name: str, data: dict):
    blob_client = get_blob_client(blob_name)
    blob_client.upload_blob(
        json.dumps(data),
        overwrite=True,
        content_settings=ContentSettings(content_type="application/json")
    )

def hash_pptx_file(file_bytes: BytesIO) -> str:
    file_bytes.seek(0)
    hasher = hashlib.sha256()
    while chunk := file_bytes.read(8192):
        hasher.update(chunk)
    file_bytes.seek(0)
    return hasher.hexdigest()

def extract_text_from_docx(file_bytes: BytesIO) -> List[str]:
    doc = Document(file_bytes)
    chunks = []
    current_chunk = []
    current_size = 0
    max_chunk_size = 1028
    min_chunk_size = 200

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        if current_size + len(text) > max_chunk_size and current_chunk:
            chunk_text = " ".join(current_chunk)
            if len(chunk_text) >= min_chunk_size:
                chunks.append(chunk_text)
            current_chunk = []
            current_size = 0

        current_chunk.append(text)
        current_size += len(text)

    if current_chunk:
        chunk_text = " ".join(current_chunk)
        if len(chunk_text) >= min_chunk_size:
            chunks.append(chunk_text)

    return chunks

def clean_extracted_text(raw_text: str) -> str:
    text = " ".join(raw_text.split())
    text = re.sub(r"(?:\b\w\s+){2,}\w\b", lambda m: m.group(0).replace(" ", ""), text)
    return text

def convert_pptx_to_pdf(input_pptx_path: str, output_dir: str) -> str:
    existing_pdfs = set(f for f in os.listdir(output_dir) if f.lower().endswith(".pdf"))

    # Suppress LibreOffice output by redirecting to DEVNULL
    subprocess.run([
        "soffice", "--headless", "--convert-to", "pdf", "--outdir", output_dir, input_pptx_path
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    new_pdfs = [f for f in os.listdir(output_dir) if f.lower().endswith(".pdf") and f not in existing_pdfs]
    if not new_pdfs:
        raise Exception("LibreOffice conversion failed: No PDF created.")

    return os.path.join(output_dir, new_pdfs[0])

def split_pdf_to_slides(input_pdf_path: str, output_pattern: str):
    subprocess.run(["pdfseparate", input_pdf_path, output_pattern], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def extract_text_from_pptx(file_bytes: BytesIO, web_url: str, server_base_url: str = None, original_filename: str = None) -> List[Dict]:
    chunks = []
    max_chunk_size = 1028
    min_chunk_size = 100
    current_chunk = []
    current_size = 0
    first_slide_number_in_chunk = None
    first_slide_url_in_chunk = None

    pptx_hash = hash_pptx_file(file_bytes)
    metadata_blob_name = f"slide_metadata/{pptx_hash}.json"

    # Download existing metadata if exists
    if blob_exists(metadata_blob_name):
        logger.info(f"Found existing metadata for hash {pptx_hash}")
        slide_metadata = download_json_from_blob(metadata_blob_name)
        slide_urls = slide_metadata["slide_urls"]
    else:
        logger.info(f"No metadata found, processing {original_filename}")
        slide_urls = []
        session_id = str(uuid.uuid4())

        with tempfile.TemporaryDirectory() as tmpdir:
            input_pptx_path = os.path.join(tmpdir, original_filename)
            with open(input_pptx_path, "wb") as f:
                f.write(file_bytes.getvalue())

            full_pdf_path = convert_pptx_to_pdf(input_pptx_path, tmpdir)
            output_pattern = os.path.join(tmpdir, "slide_%d.pdf")
            split_pdf_to_slides(full_pdf_path, output_pattern)

            slide_pdfs = sorted([f for f in os.listdir(tmpdir) if re.match(r"slide_\d+\.pdf", f)])
            for idx, pdf_name in enumerate(slide_pdfs):
                src_pdf = os.path.join(tmpdir, pdf_name)
                blob_key = f"slides/{session_id}/{pdf_name}"

                with open(src_pdf, "rb") as data:
                    blob_client = get_blob_client(blob_key)
                    blob_client.upload_blob(
                        data,
                        overwrite=True,
                        content_settings=ContentSettings(content_type="application/pdf")
                    )

                slide_urls.append(blob_client.url)

        upload_json_to_blob(metadata_blob_name, {"slide_urls": slide_urls})
        logger.info(f"Saved metadata JSON for {pptx_hash}")

    # Process slides for text extraction
    with tempfile.TemporaryDirectory() as tmpdir:
        input_pptx_path = os.path.join(tmpdir, original_filename)
        with open(input_pptx_path, "wb") as f:
            f.write(file_bytes.getvalue())

        full_pdf_path = convert_pptx_to_pdf(input_pptx_path, tmpdir)
        output_pattern = os.path.join(tmpdir, "slide_%d.pdf")
        split_pdf_to_slides(full_pdf_path, output_pattern)

        slide_pdfs = sorted([f for f in os.listdir(tmpdir) if re.match(r"slide_\d+\.pdf", f)])

        for idx, pdf_name in enumerate(slide_pdfs):
            slide_number = int(re.search(r'slide_(\d+)\.pdf', pdf_name).group(1))
            this_slide_url = slide_urls[idx]

            src_pdf = os.path.join(tmpdir, pdf_name)
            extracted_text_file = os.path.join(tmpdir, f"{pdf_name}.txt")
            try:
                subprocess.run(["pdftotext", src_pdf, extracted_text_file], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                with open(extracted_text_file, "r", encoding="utf-8") as txt_file:
                    slide_text = txt_file.read().strip()
            except Exception as e:
                logger.warning(f"Failed to extract text from {pdf_name}: {e}")
                slide_text = ""

            if not slide_text:
                slide_text = f"(No text content extracted from slide {slide_number})"
            else:
                slide_text = clean_extracted_text(slide_text)

            slide_content = f"[Slide {slide_number}] {slide_text}"
            slide_size = len(slide_content)

            if not current_chunk:
                first_slide_number_in_chunk = slide_number
                first_slide_url_in_chunk = this_slide_url

            if current_size + slide_size > max_chunk_size and current_chunk:
                chunk_text = " ".join(current_chunk)
                if len(chunk_text) >= min_chunk_size:
                    chunks.append({
                        "content": chunk_text,
                        "slide_number": first_slide_number_in_chunk,
                        "slide_url": first_slide_url_in_chunk
                    })
                current_chunk = []
                current_size = 0
                first_slide_number_in_chunk = slide_number
                first_slide_url_in_chunk = this_slide_url

            current_chunk.append(slide_content)
            current_size += slide_size

        if current_chunk:
            chunk_text = " ".join(current_chunk)
            if len(chunk_text) >= min_chunk_size:
                chunks.append({
                    "content": chunk_text,
                    "slide_number": first_slide_number_in_chunk,
                    "slide_url": first_slide_url_in_chunk
                })

    return chunks

def detect_file_type(binary_data: bytes) -> str:
    """Detect file type based on binary signature"""
    # Check for ZIP-based formats (docx, pptx)
    if binary_data.startswith(b'PK\x03\x04'):
        # It's a ZIP file, check for specific Office formats
        try:
            with zipfile.ZipFile(BytesIO(binary_data), 'r') as zip_file:
                file_list = zip_file.namelist()
                if 'word/document.xml' in file_list:
                    return 'docx'
                elif 'ppt/presentation.xml' in file_list:
                    return 'pptx'
        except:
            pass
    
    # Check for PDF
    if binary_data.startswith(b'%PDF'):
        return 'pdf'
    
    return 'unknown'

def parse_arguments():
    """Parse command line arguments correctly based on NiFi configuration"""
    filename = None
    web_url = None
    
    # Method 1: Check if arguments are passed as separate parameters
    if len(sys.argv) >= 3:
        filename = sys.argv[1]
        web_url = sys.argv[2]
        logger.info(f"Parsed from separate args: filename={filename}, web_url={web_url}")
    elif len(sys.argv) == 2:
        # Method 2: Check if arguments are passed as a single semicolon-separated string
        arg_string = sys.argv[1]
        if ';' in arg_string:
            parts = arg_string.split(';')
            if len(parts) >= 2:
                filename = parts[0]
                web_url = parts[1]
                logger.info(f"Parsed from semicolon-separated args: filename={filename}, web_url={web_url}")
        else:
            # Single argument, treat as filename
            filename = arg_string
            web_url = arg_string
            logger.info(f"Single argument provided: {filename}")
    
    # Method 3: Check environment variables as fallback
    if not filename:
        filename = os.environ.get('filename', os.environ.get('onedrive_filename', 'unknown_file'))
        logger.info(f"Got filename from environment: {filename}")
    
    if not web_url:
        web_url = os.environ.get('web_url', filename)
        logger.info(f"Got web_url from environment or defaulted to filename: {web_url}")
    
    return filename, web_url

def main():
    try:
        # Parse arguments correctly
        filename, web_url = parse_arguments()
        
        # Read binary data from stdin
        binary_data = sys.stdin.buffer.read()
        
        if not binary_data:
            raise ValueError("No input data received")
        
        # Detect file type if filename doesn't have extension
        if '.' not in filename:
            detected_type = detect_file_type(binary_data)
            if detected_type != 'unknown':
                filename = f"{filename}.{detected_type}"
        
        # Create BytesIO object
        file_bytes = BytesIO(binary_data)
        
        # Process based on file type
        filename_lower = filename.lower()
        
        if filename_lower.endswith(".docx"):
            chunks = extract_text_from_docx(file_bytes)
            file_type = "docx"
        elif filename_lower.endswith(".pptx"):
            chunks = extract_text_from_pptx(file_bytes, web_url, original_filename=filename)
            file_type = "pptx"
        else:
            # Try to detect from binary data
            detected_type = detect_file_type(binary_data)
            if detected_type == 'docx':
                chunks = extract_text_from_docx(file_bytes)
                file_type = "docx"
            elif detected_type == 'pptx':
                chunks = extract_text_from_pptx(file_bytes, web_url, original_filename=filename)
                file_type = "pptx"
            else:
                raise ValueError(f"Unsupported file type: {filename}")

        # Prepare output
        chunk_output = []
        for idx, chunk in enumerate(chunks):
            if isinstance(chunk, dict):
                text = chunk.get("content", "")
                slide_number = chunk.get("slide_number")
                slide_url = chunk.get("slide_url")
            else:
                text = str(chunk)
                slide_number = None
                slide_url = None

            # Clean text
            cleaned_text = " ".join(text.split())
            cleaned_text = "".join(char for char in cleaned_text if ord(char) < 128)

            # Create metadata
            metadata = {
                "source_file": filename,
                "file_type": file_type,
                "chunk_index": idx,
                "filepath": web_url  # This should now be different from filename
            }
            if slide_number is not None:
                metadata["slide_number"] = slide_number
            if slide_url is not None:
                metadata["slide_url"] = slide_url

            chunk_output.append({"content": cleaned_text, "metadata": metadata})

        # Output result as JSON - ensure clean output
        result = {"chunks": chunk_output}
        json_output = json.dumps(result, ensure_ascii=True)
        
        # Clear stdout buffer and output only JSON
        sys.stdout.flush()
        print(json_output, flush=True)
        
        # Log success to stderr
        logger.info(f"Successfully processed {len(chunk_output)} chunks from {filename} with web_url: {web_url}")

    except Exception as e:
        logger.error(f"Text extraction failed: {str(e)}")
        error_result = {"error": str(e), "status": "failed"}
        print(json.dumps(error_result))
        sys.exit(1)

if __name__ == "__main__":
    main()