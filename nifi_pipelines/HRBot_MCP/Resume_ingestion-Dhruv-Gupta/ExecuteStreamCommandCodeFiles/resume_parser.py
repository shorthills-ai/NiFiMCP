import os
import sys
import json
import re
import fitz  # PyMuPDF
import cv2
from PIL import Image
from pathlib import Path
from pdf2image import convert_from_path
import pytesseract
from llama_parse import LlamaParse
from dotenv import load_dotenv
import os

# ✅ Load .env file from current directory
load_dotenv()



class ResumeParser:
    def __init__(self):
        api_key =os.getenv("LLAMA_CLOUD_API_KEY")
        if not api_key:
            raise EnvironmentError("❌ LLAMA_CLOUD_API_KEY is not set.")
        
        self.parser = LlamaParse(
            api_key=api_key,
            result_type="markdown",
            do_not_unroll_columns=True
        )
        self.SUPPORTED_EXTENSIONS = [".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png"]

    def extract_links_from_text(self, text):
        url_pattern = r'(https?://[^\s]+|www\.[^\s]+)'
        urls = re.findall(url_pattern, text)
        return [{"text": url, "uri": url} for url in urls]

    def extract_links_from_pdf(self, file_path):
        links = []
        try:
            with fitz.open(file_path) as doc:
                for page in doc:
                    for link in page.get_links():
                        if "uri" in link:
                            text = page.get_textbox(link.get("from", ())).strip()
                            links.append({"text": text, "uri": link["uri"]})
        except Exception as e:
            print(f"⚠️ Failed to extract links from PDF: {e}", file=sys.stderr)
        return links

    def extract_text_from_pdf_ocr(self, pdf_path):
        try:
            images = convert_from_path(pdf_path, dpi=300)
        except Exception as e:
            print(f"❌ Failed to convert PDF to images (OCR): {e}", file=sys.stderr)
            return ""

        text = ""
        for i, image in enumerate(images):
            try:
                text += f"\n\n--- Page {i+1} ---\n\n"
                text += pytesseract.image_to_string(image)
            except Exception as e:
                print(f"⚠️ OCR failed on page {i+1}: {e}", file=sys.stderr)
        return text.strip()

    def extract_text_from_image(self, image_path):
        try:
            img = cv2.imread(str(image_path))
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            pil_img = Image.fromarray(gray)
            return pytesseract.image_to_string(pil_img).strip()
        except Exception as e:
            print(f"❌ OCR failed for image {image_path}: {e}", file=sys.stderr)
            return ""

    def _merge_links(self, links1, links2):
        seen = set()
        merged = []
        for link in links1 + links2:
            uri = link.get("uri")
            if uri and uri not in seen:
                merged.append(link)
                seen.add(uri)
        return merged

    def parse(self, file_path):
        ext = os.path.splitext(file_path)[-1].lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}")

        file_name = os.path.basename(file_path)
        llama_content = ""
        ocr_content = ""
        llama_links = []
        ocr_links = []

        # Run LlamaParse if supported
        if ext in [".pdf", ".docx", ".doc"]:
            try:
                documents = self.parser.load_data(file_path)
                llama_content = "\n".join(doc.text for doc in documents).strip()
                llama_links = self.extract_links_from_pdf(file_path)
            except Exception as e:
                print(f"⚠️ LlamaParse failed for {file_name}: {e}", file=sys.stderr)

        # Run OCR if PDF or image
        if ext == ".pdf":
            ocr_content = self.extract_text_from_pdf_ocr(file_path)
            ocr_links = self.extract_links_from_text(ocr_content)
        elif ext in [".jpg", ".jpeg", ".png"]:
            ocr_content = self.extract_text_from_image(file_path)
            ocr_links = self.extract_links_from_text(ocr_content)

        links = self._merge_links(llama_links, ocr_links)

        if not llama_content.strip() and not ocr_content.strip():
            raise ValueError(f"❌ Failed to extract content from: {file_name}")

        links = json.dumps(links, ensure_ascii=False)

        return {
            "file": file_name,
            "content": {
                "llama": llama_content,
                "ocr": ocr_content
            },
            "links": links
        }


def main():
    try:
        if len(sys.argv) < 2:
            raise ValueError("❌ Please provide a file path as the first argument.")

        file_path = sys.argv[1]
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"❌ File does not exist: {file_path}")

        parser = ResumeParser()
        result = parser.parse(file_path)

        # Output result to stdout for NiFi
        print(json.dumps(result, ensure_ascii=False))

        # Extract employee_id from filename (e.g., 110023 from 110023.pdf)
        file_name = os.path.basename(file_path)
        employee_id = os.path.splitext(file_name)[0]

        # Write to a uniquely named file using employee_id
        output_dir = Path("/home/nifi/nifi2/users/dhruv/hrbotingestion/data")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{employee_id}.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
