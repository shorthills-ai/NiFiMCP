#!/usr/bin/env python3
import requests
import base64
import json
import os
import shutil
import tempfile
import zipfile
import sys
from datetime import datetime
from urllib.parse import unquote, parse_qs, urlparse
from pptx import Presentation
import xml.etree.ElementTree as ET
import re
from typing import List, Set, Dict, Any
import warnings
import argparse

# Suppress urllib3 warning
warnings.filterwarnings('ignore', category=Warning)

class NiFiPPTProcessor:
    def __init__(self, client_id: str, client_secret: str, tenant_id: str, 
                 target_ppt_path: str, nifi_temp_dir: str = None):
        """
        Initialize the NiFi PPT processor
        
        Args:
            client_id: Azure AD app client ID
            client_secret: Azure AD app client secret
            tenant_id: Azure AD tenant ID
            target_ppt_path: Path to the target PowerPoint file where slides will be copied
            nifi_temp_dir: NiFi temp directory (will use system temp if not provided)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.target_ppt_path = target_ppt_path
        self.access_token = None
        
        # Set up NiFi temp directory
        if nifi_temp_dir and os.path.exists(nifi_temp_dir):
            self.temp_dir = nifi_temp_dir
        else:
            self.temp_dir = tempfile.gettempdir()
        
        # Create downloads subdirectory in temp
        self.downloads_dir = os.path.join(self.temp_dir, "nifi_ppt_downloads")
        os.makedirs(self.downloads_dir, exist_ok=True)
        
        # Validate target file exists
        if not os.path.exists(target_ppt_path):
            raise FileNotFoundError(f"Target PowerPoint file not found: {target_ppt_path}")
    
    def log_message(self, message: str, level: str = "INFO"):
        """Log messages to stderr for NiFi visibility"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}", file=sys.stderr)
        # Also print to stdout for pipeline flow
        print(f"[{level}] {message}")
    
    def get_access_token(self) -> bool:
        """Get access token using client credentials flow"""
        try:
            url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
            data = {
                'grant_type': 'client_credentials',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'scope': 'https://graph.microsoft.com/.default'
            }
            response = requests.post(url, data=data)
            response.raise_for_status()
            self.access_token = response.json()['access_token']
            self.log_message("Access token obtained successfully")
            return True
        except Exception as e:
            self.log_message(f"Error getting access token: {e}", "ERROR")
            if hasattr(e, 'response'):
                self.log_message(f"Response status: {e.response.status_code}", "ERROR")
                self.log_message(f"Response text: {e.response.text}", "ERROR")
            return False
    
    def encode_share_url(self, web_url: str) -> str:
        """Encode SharePoint URL for Graph API"""
        try:
            parsed_url = urlparse(web_url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
            
            query = parse_qs(parsed_url.query)
            if 'sourcedoc' in query:
                file_id = query['sourcedoc'][0].strip('{}')
                clean_url = f"{base_url}?sourcedoc={{{file_id}}}"
            else:
                clean_url = base_url
                
            base64_url = base64.b64encode(clean_url.encode('utf-8')).decode('utf-8')
            return base64_url.replace('/', '_').replace('+', '-').rstrip('=')
        except Exception as e:
            self.log_message(f"Error encoding URL: {e}", "ERROR")
            return None
    
    def get_download_url(self, encoded_url: str) -> tuple:
        """Get download URL using Graph API"""
        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json"
            }
            url = f"https://graph.microsoft.com/v1.0/shares/u!{encoded_url}/driveItem"
            
            self.log_message("Requesting file metadata from Graph API...")
            response = requests.get(url, headers=headers)
            
            if response.status_code == 401:
                self.log_message("Token expired or invalid. Please check your credentials.", "ERROR")
                return None, None
            elif response.status_code == 403:
                self.log_message("Access forbidden. Please check your permissions.", "ERROR")
                self.log_message("Make sure your app has 'Files.Read.All' permission.", "ERROR")
                return None, None
                
            response.raise_for_status()
            data = response.json()
            
            if "@microsoft.graph.downloadUrl" not in data:
                self.log_message("Download URL not found in response", "ERROR")
                return None, None
                
            return data["@microsoft.graph.downloadUrl"], data["name"]
        except requests.exceptions.RequestException as e:
            self.log_message(f"Error getting download URL: {e}", "ERROR")
            if hasattr(e, 'response'):
                self.log_message(f"Response status: {e.response.status_code}", "ERROR")
                self.log_message(f"Response text: {e.response.text}", "ERROR")
            return None, None
    
    def download_file(self, download_url: str, filename: str) -> str:
        """Download file with progress tracking"""
        try:
            if not download_url or not filename:
                return None
                
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name, ext = os.path.splitext(filename)
            output_filename = f"{base_name}_{timestamp}{ext}"
            output_path = os.path.join(self.downloads_dir, output_filename)
            
            self.log_message(f"Downloading file to: {output_path}")
            response = requests.get(download_url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            block_size = 8192
            downloaded = 0
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=block_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            if downloaded % (block_size * 100) == 0:  # Log progress every MB
                                self.log_message(f"Download progress: {percent:.1f}%")
            
            self.log_message("File downloaded successfully!")
            return output_path
        except Exception as e:
            self.log_message(f"Error downloading file: {e}", "ERROR")
            return None
    
    def copy_single_slide_optimized(self, source_ppt_path: str, slide_index: int, output_path: str = None) -> str:
        """
        Optimized function to copy ONLY a specific slide with its dependencies
        """
        
        if not os.path.exists(source_ppt_path):
            raise FileNotFoundError(f"Source file not found: {source_ppt_path}")
        if not os.path.exists(self.target_ppt_path):
            raise FileNotFoundError(f"Target file not found: {self.target_ppt_path}")
        
        source_prs = Presentation(source_ppt_path)
        if slide_index < 0 or slide_index >= len(source_prs.slides):
            raise IndexError(f"Slide index {slide_index} out of range. Source has {len(source_prs.slides)} slides.")
        
        if output_path is None:
            output_path = self.target_ppt_path
        
        self.log_message(f"Starting optimized copy of slide {slide_index + 1}...")
        
        slide_data = self._extract_single_slide_data(source_ppt_path, slide_index)
        
        target_prs = Presentation(self.target_ppt_path)
        next_slide_num = len(target_prs.slides) + 1
        
        self._insert_slide_into_target(self.target_ppt_path, slide_data, next_slide_num, output_path)
        
        self.log_message(f"Successfully copied slide {slide_index + 1} to position {next_slide_num}")
        return output_path
    
    def _extract_single_slide_data(self, source_ppt_path: str, slide_index: int) -> Dict:
        """Extract only the data needed for a specific slide"""
        
        slide_data = {
            'slide_xml': None,
            'slide_rels_xml': None,
            'media_files': {},
            'slide_number': slide_index + 1
        }
        
        with zipfile.ZipFile(source_ppt_path, 'r') as source_zip:
            slide_xml_path = f"ppt/slides/slide{slide_index + 1}.xml"
            try:
                slide_data['slide_xml'] = source_zip.read(slide_xml_path).decode('utf-8')
            except KeyError:
                raise FileNotFoundError(f"Slide {slide_index + 1} not found in source presentation")
            
            slide_rels_path = f"ppt/slides/_rels/slide{slide_index + 1}.xml.rels"
            try:
                slide_data['slide_rels_xml'] = source_zip.read(slide_rels_path).decode('utf-8')
                
                referenced_media = self._get_referenced_media_files(slide_data['slide_rels_xml'])
                
                for media_file in referenced_media:
                    media_path = f"ppt/media/{media_file}"
                    try:
                        slide_data['media_files'][media_file] = source_zip.read(media_path)
                        self.log_message(f"Extracted media file: {media_file}")
                    except KeyError:
                        self.log_message(f"Warning: Referenced media file not found: {media_file}", "WARN")
                        
            except KeyError:
                self.log_message(f"No media relationships found for slide {slide_index + 1}")
        
        return slide_data
    
    def _get_referenced_media_files(self, slide_rels_xml: str) -> Set[str]:
        """Parse slide relationships XML to find only the media files referenced by this specific slide"""
        
        media_files = set()
        
        try:
            root = ET.fromstring(slide_rels_xml)
            
            for relationship in root.findall(".//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
                target_attr = relationship.get("Target")
                if target_attr and ("../media/" in target_attr or "media/" in target_attr):
                    media_filename = os.path.basename(target_attr)
                    media_files.add(media_filename)
                    
        except ET.ParseError as e:
            self.log_message(f"Warning: Could not parse slide relationships: {e}", "WARN")
        
        return media_files
    
    def _insert_slide_into_target(self, target_ppt_path: str, slide_data: Dict, new_slide_num: int, output_path: str):
        """Insert the slide data into target presentation with minimal processing"""
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as temp_file:
            temp_path = temp_file.name
        
        try:
            shutil.copy2(target_ppt_path, temp_path)
            
            with zipfile.ZipFile(temp_path, 'a') as target_zip:
                
                slide_xml_path = f"ppt/slides/slide{new_slide_num}.xml"
                target_zip.writestr(slide_xml_path, slide_data['slide_xml'])
                
                if slide_data['slide_rels_xml']:
                    slide_rels_path = f"ppt/slides/_rels/slide{new_slide_num}.xml.rels"
                    target_zip.writestr(slide_rels_path, slide_data['slide_rels_xml'])
                
                for media_filename, media_content in slide_data['media_files'].items():
                    media_path = f"ppt/media/{media_filename}"
                    
                    try:
                        existing_content = target_zip.read(media_path)
                        if existing_content == media_content:
                            self.log_message(f"Media file {media_filename} already exists (identical)")
                            continue
                    except KeyError:
                        pass
                    
                    target_zip.writestr(media_path, media_content)
                    self.log_message(f"Added media file: {media_filename}")
            
            self._update_presentation_structure_minimal(temp_path, new_slide_num)
            
            shutil.move(temp_path, output_path)
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def _update_presentation_structure_minimal(self, pptx_path: str, new_slide_num: int):
        """Update only the necessary structure files for the new slide"""
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(pptx_path, 'r') as zip_ref:
                files_to_update = [
                    "ppt/presentation.xml",
                    "ppt/_rels/presentation.xml.rels",
                    "[Content_Types].xml"
                ]
                
                for file_path in files_to_update:
                    try:
                        zip_ref.extract(file_path, temp_dir)
                    except KeyError:
                        self.log_message(f"Warning: {file_path} not found in presentation", "WARN")
            
            self._update_presentation_xml(os.path.join(temp_dir, "ppt", "presentation.xml"), new_slide_num)
            self._update_presentation_rels(os.path.join(temp_dir, "ppt", "_rels", "presentation.xml.rels"), new_slide_num)
            self._update_content_types(os.path.join(temp_dir, "[Content_Types].xml"), new_slide_num)
            
            with zipfile.ZipFile(pptx_path, 'a') as zip_ref:
                for file_path in files_to_update:
                    full_path = os.path.join(temp_dir, file_path)
                    if os.path.exists(full_path):
                        zip_ref.write(full_path, file_path)
    
    def _update_presentation_xml(self, file_path: str, new_slide_num: int):
        """Update presentation.xml to include new slide"""
        if not os.path.exists(file_path):
            return
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        new_slide_id = 256 + new_slide_num
        new_slide_entry = f'<p:sldId id="{new_slide_id}" r:id="rId{new_slide_num + 1}"/>'
        
        slide_pattern = r'(<p:sldIdLst[^>]*>)(.*?)(</p:sldIdLst>)'
        match = re.search(slide_pattern, content, re.DOTALL)
        if match:
            updated_content = content.replace(
                match.group(0),
                f"{match.group(1)}{match.group(2)}{new_slide_entry}{match.group(3)}"
            )
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(updated_content)
    
    def _update_presentation_rels(self, file_path: str, new_slide_num: int):
        """Update presentation relationships"""
        if not os.path.exists(file_path):
            return
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        new_rel = f'<Relationship Id="rId{new_slide_num + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{new_slide_num}.xml"/>'
        
        updated_content = content.replace('</Relationships>', f'{new_rel}</Relationships>')
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(updated_content)
    
    def _update_content_types(self, file_path: str, new_slide_num: int):
        """Update content types"""
        if not os.path.exists(file_path):
            return
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        new_override = f'<Override PartName="/ppt/slides/slide{new_slide_num}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        
        updated_content = content.replace('</Types>', f'{new_override}</Types>')
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(updated_content)
    
    def process_nifi_input(self, input_json: str) -> str:
        """
        Process JSON input from NiFi and return the path to generated PPT file
        
        Args:
            input_json: JSON string from NiFi flow
            
        Returns:
            Path to the generated PowerPoint file, or None if failed
        """
        
        # Parse input JSON
        try:
            data = json.loads(input_json)
        except Exception as e:
            self.log_message(f"Failed to parse input JSON: {e}", "ERROR")
            raise Exception(f"Failed to parse input JSON: {e}")
        
        # Support both list and dict input
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("extracted_items", [])
        else:
            items = []
        
        # Generate output file path in temp directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"nifi_processed_presentation_{timestamp}.pptx"
        output_path = os.path.join(self.temp_dir, output_filename)
        
        self.log_message(f"Output will be saved to: {output_path}")
        
        # Initialize access token
        if not self.get_access_token():
            raise Exception("Failed to get access token")
        
        # Copy target file to output path initially
        try:
            shutil.copy2(self.target_ppt_path, output_path)
            self.log_message(f"Created output file: {output_path}")
        except Exception as e:
            error_msg = f"Failed to create output file: {e}"
            self.log_message(error_msg, "ERROR")
            raise Exception(error_msg)
        
        processed_count = 0
        skipped_count = 0
        error_count = 0
        
        # Process each item in the JSON
        for item in items:
            source_file = item.get("source_file", "")
            slide_number = item.get("slide_number")
            link = item.get("link", "")
            content_summary = item.get("content_summary", "")
            
            self.log_message(f"Processing: {source_file}")
            
            # Skip if not a PPTX file or no slide number
            if not source_file.lower().endswith('.pptx') or slide_number is None:
                self.log_message(f"Skipping {source_file} (not PPTX or no slide number)", "WARN")
                skipped_count += 1
                continue
            
            # Skip if no link provided
            if not link:
                self.log_message(f"Skipping {source_file} (no download link)", "WARN")
                skipped_count += 1
                continue
            
            try:
                # Process the file
                encoded_url = self.encode_share_url(link)
                if not encoded_url:
                    raise Exception("Failed to encode URL")
                
                download_url, filename = self.get_download_url(encoded_url)
                if not download_url:
                    raise Exception("Failed to get download URL")
                
                downloaded_file_path = self.download_file(download_url, filename)
                if not downloaded_file_path:
                    raise Exception("Failed to download file")
                
                slide_index = slide_number - 1
                
                self.copy_single_slide_optimized(
                    source_ppt_path=downloaded_file_path,
                    slide_index=slide_index,
                    output_path=output_path
                )

                # Clean up downloaded file
                try:
                    os.remove(downloaded_file_path)
                    self.log_message(f"Deleted downloaded file: {downloaded_file_path}")
                except Exception as del_err:
                    self.log_message(f"Warning: Could not delete downloaded file: {del_err}", "WARN")
                
                processed_count += 1
                self.log_message(f"Successfully processed {source_file}, slide {slide_number}")
                
            except Exception as e:
                error_msg = f"Failed to process {source_file}: {str(e)}"
                self.log_message(error_msg, "ERROR")
                error_count += 1
        
        # Final summary
        self.log_message(f"Processing Summary - Processed: {processed_count}, "
                        f"Skipped: {skipped_count}, Errors: {error_count}")
        
        if processed_count == 0 and error_count > 0:
            raise Exception("No slides were processed successfully")
        
        return output_path


def main():
    """Main function for NiFi ExecuteStreamCommand - outputs PowerPoint file directly"""
    parser = argparse.ArgumentParser(description="NiFi JSON to PPTX slide copier (local or NiFi mode)")
    parser.add_argument('--json', required=False, help='Path to the input JSON file (for local testing)')
    parser.add_argument('--output', required=False, help='Path to save the output PPTX file (for local testing)')
    args = parser.parse_args()

    # Configuration - these should be set as environment variables in NiFi
    client_id = os.getenv('AZURE_CLIENT_ID')
    client_secret = os.getenv('AZURE_CLIENT_SECRET')
    tenant_id = os.getenv('AZURE_TENANT_ID')
    target_ppt_path = os.getenv('TARGET_PPT_PATH', 'Hpm_test.pptx')
    nifi_temp_dir = os.getenv('NIFI_TEMP_DIR', None)

    if not all([client_id, client_secret, tenant_id, target_ppt_path]):
        print("Missing required environment variables!", file=sys.stderr)
        sys.exit(1)

    try:
        # Initialize processor
        processor = NiFiPPTProcessor(
            client_id=client_id,
            client_secret=client_secret,
            tenant_id=tenant_id,
            target_ppt_path=target_ppt_path,
            nifi_temp_dir=nifi_temp_dir
        )

        # Local testing mode: --json and --output provided
        if args.json:
            with open(args.json, 'r', encoding='utf-8') as f:
                input_json = f.read()
            output_ppt_path = args.output or os.path.join(processor.temp_dir, f"local_processed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pptx")
            result_ppt_path = processor.process_nifi_input(input_json)
            shutil.copy2(result_ppt_path, output_ppt_path)
            print(f"[SUCCESS] Output PPTX saved to: {output_ppt_path}")
            # Clean up temp file
            try:
                os.remove(result_ppt_path)
            except Exception:
                pass
            sys.exit(0)

        # NiFi mode: read from stdin, write to stdout
        else:
            # Read JSON input from stdin (NiFi flow)
            try:
                input_json = sys.stdin.read().strip()
                if not input_json:
                    print("ERROR: No input received from stdin", file=sys.stderr)
                    sys.exit(1)
            except Exception as e:
                print(f"ERROR: Failed to read stdin: {e}", file=sys.stderr)
                sys.exit(1)

            # Process input and get output file path
            output_ppt_path = processor.process_nifi_input(input_json)

            # Read the generated PowerPoint file and write it to stdout (binary mode)
            with open(output_ppt_path, 'rb') as ppt_file:
                sys.stdout.buffer.write(ppt_file.read())
            # Clean up the temporary file
            try:
                os.remove(output_ppt_path)
                print(f"Cleaned up temporary file: {output_ppt_path}", file=sys.stderr)
            except Exception as cleanup_err:
                print(f"Warning: Could not clean up temporary file: {cleanup_err}", file=sys.stderr)
            sys.exit(0)

    except Exception as e:
        print(f"FATAL ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()


