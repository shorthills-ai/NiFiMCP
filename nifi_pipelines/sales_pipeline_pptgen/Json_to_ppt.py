#!/usr/bin/env python3
"""
NiFi PowerPoint Processor Script
Processes JSON input from NiFi flow, downloads PowerPoint files from SharePoint,
extracts specific slides, and outputs the final merged PowerPoint file.

Usage in NiFi ExecuteStreamCommand:
Command: python3
Arguments: nifi_pipline.py
Working Directory: /path/to/script/directory
Environment Variables:
  AZURE_CLIENT_ID=your_client_id
  AZURE_CLIENT_SECRET=your_client_secret
  AZURE_TENANT_ID=your_tenant_id
  NIFI_TEMP_DIR=/tmp/nifi_ppt_processing
"""

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
from typing import List, Set, Dict, Any, Optional
import warnings
import argparse
import traceback
from dotenv import load_dotenv
load_dotenv()  # Commented out for NiFi deployment - using environment variables from NiFi

# Suppress urllib3 warnings
warnings.filterwarnings('ignore', category=Warning)

# Fix SSL warnings for macOS LibreSSL
import ssl
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

class NiFiPPTProcessor:
    """
    NiFi-integrated PowerPoint processor for downloading SharePoint files
    and merging specific slides into a target presentation.
    """
    
    def __init__(self, client_id: str, client_secret: str, tenant_id: str, nifi_temp_dir: Optional[str] = None):
        """
        Initialize the NiFi PPT processor
        
        Args:
            client_id: Azure AD app client ID
            client_secret: Azure AD app client secret
            tenant_id: Azure AD tenant ID
            nifi_temp_dir: NiFi temp directory (will use local temp if not provided)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.access_token = None
        
        # Set up temp directory - use NiFi's temp directory or create local one
        if nifi_temp_dir and os.path.exists(nifi_temp_dir):
            self.temp_dir = nifi_temp_dir
        else:
            # Use system temp directory (NiFi's default) or create in current directory
            try:
                # Try to use system temp directory first
                self.temp_dir = os.path.join(tempfile.gettempdir(), f"nifi_ppt_processing_{os.getpid()}")
            except:
                # Fallback to current directory
                self.temp_dir = os.path.join(os.getcwd(), "temp_pptx_processing")
        
        # Create downloads subdirectory in temp
        self.downloads_dir = os.path.join(self.temp_dir, "nifi_ppt_downloads")
        os.makedirs(self.downloads_dir, exist_ok=True)
        
        # Add file cache to avoid duplicate downloads
        self.file_cache = {}  # {source_file: downloaded_file_path}
        
        # Add slide deduplication cache
        self.slide_cache = {}  # {(source_file, slide_number): slide_hash}
        
        self.log_message(f"Temp directory created at: {self.temp_dir}")
    
    def log_message(self, message: str, level: str = "INFO"):
        """Log messages to stderr for NiFi visibility"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}", file=sys.stderr)
    
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
            if hasattr(e, 'response') and e.response:
                self.log_message(f"Response status: {e.response.status_code}", "ERROR")
                self.log_message(f"Response text: {e.response.text}", "ERROR")
            return False
    
    def encode_share_url(self, web_url: str) -> Optional[str]:
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
            if hasattr(e, 'response') and e.response:
                self.log_message(f"Response status: {e.response.status_code}", "ERROR")
                self.log_message(f"Response text: {e.response.text}", "ERROR")
            return None, None
    
    def generate_slide_hash(self, extract_path, slide_number):
        """
        Generate a hash of the slide content to identify duplicates.
        Reads the actual slide XML content for accurate comparison.
        """
        try:
            slides_dir = os.path.join(extract_path, "ppt", "slides")
            slide_file = os.path.join(slides_dir, f'slide{slide_number}.xml')
            
            if os.path.exists(slide_file):
                # Read slide XML content
                with open(slide_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Also include slide relationships for more accurate hash
                slides_rels_dir = os.path.join(extract_path, "ppt", "slides", "_rels")
                rels_file = os.path.join(slides_rels_dir, f'slide{slide_number}.xml.rels')
                if os.path.exists(rels_file):
                    with open(rels_file, 'r', encoding='utf-8') as f:
                        rels_content = f.read()
                    content += rels_content
                
                return hash(content)
            return None
        except Exception as e:
            self.log_message(f"Error generating slide hash: {e}", "WARN")
            return None

    def is_duplicate_slide(self, source_file, slide_number, extract_path):
        """
        Check if this slide has already been processed.
        Returns True if duplicate, False if new.
        """
        slide_key = (source_file, slide_number)
        current_hash = self.generate_slide_hash(extract_path, slide_number)
        
        if current_hash is None:
            return False  # Can't determine, process it
        
        if slide_key in self.slide_cache:
            cached_hash = self.slide_cache[slide_key]
            if current_hash == cached_hash:
                self.log_message(f"Duplicate slide detected: {source_file} slide {slide_number}")
                return True
        
        # Add to cache
        self.slide_cache[slide_key] = current_hash
        return False

    def get_or_download_file(self, source_file: str, link: str) -> Optional[str]:
        """
        Get a file from cache if already downloaded, otherwise download it.
        This prevents duplicate downloads of the same file.
        """
        # Check if file is already in cache
        if source_file in self.file_cache:
            cached_path = self.file_cache[source_file]
            if os.path.exists(cached_path):
                self.log_message(f"Using cached file for {source_file}: {os.path.basename(cached_path)}")
                return cached_path
            else:
                # Cached file doesn't exist, remove from cache
                del self.file_cache[source_file]
                self.log_message(f"Removed invalid cache entry for {source_file}")
        
        # File not in cache, download it
        self.log_message(f"Downloading new file: {source_file}")
        encoded_url = self.encode_share_url(link)
        if not encoded_url:
            self.log_message(f"Failed to encode SharePoint URL for {source_file}", "ERROR")
            return None
        
        download_url, filename = self.get_download_url(encoded_url)
        if not download_url:
            self.log_message(f"Failed to get download URL for {source_file}", "ERROR")
            return None
        
        downloaded_file_path = self.download_file(download_url, filename)
        if not downloaded_file_path:
            self.log_message(f"Failed to download file {source_file}", "ERROR")
            return None
        
        # Verify downloaded file exists
        if not os.path.exists(downloaded_file_path):
            self.log_message(f"Downloaded file not found: {downloaded_file_path}", "ERROR")
            return None
        
        # Add to cache
        self.file_cache[source_file] = downloaded_file_path
        self.log_message(f"Added {source_file} to cache: {os.path.basename(downloaded_file_path)} ({os.path.getsize(downloaded_file_path)} bytes)")
        
        return downloaded_file_path

    def download_file(self, download_url: str, filename: str) -> Optional[str]:
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
                            if downloaded % (block_size * 100) == 0:  # Log progress every ~800KB
                                self.log_message(f"Download progress: {percent:.1f}%")
            
            self.log_message("File downloaded successfully!")
            return output_path
        except Exception as e:
            self.log_message(f"Error downloading file: {e}", "ERROR")
            return None
    
    def copy_single_slide(self, input_file, output_file, slide_number):
        """
        Copy a specific slide from a PPTX file to create a new PPTX file (single-slide, valid for PowerPoint),
        and copy all referenced media files.
        """
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"Input file '{input_file}' not found.")
        if not input_file.lower().endswith('.pptx'):
            raise ValueError("Input file must be a .pptx file")
        with tempfile.TemporaryDirectory() as temp_dir:
            extract_path = os.path.join(temp_dir, "extracted")
            output_path = os.path.join(temp_dir, "output")
            with zipfile.ZipFile(input_file, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            slides_dir = os.path.join(extract_path, "ppt", "slides")
            slide_files = [f for f in os.listdir(slides_dir) if f.startswith('slide') and f.endswith('.xml')]
            slide_files.sort(key=lambda x: int(re.search(r'slide(\d+)\.xml', x).group(1)))
            if slide_number < 1 or slide_number > len(slide_files):
                raise ValueError(f"Slide number {slide_number} not found. Available slides: 1-{len(slide_files)}")
            target_slide = slide_files[slide_number - 1]
            target_slide_num = re.search(r'slide(\d+)\.xml', target_slide).group(1)
            
            # Create output directory and copy complete structure
            os.makedirs(output_path, exist_ok=True)
            self.copy_complete_structure(extract_path, output_path)
            
            # --- FIXED: Copy media files BEFORE cleaning slides directory ---
            # Comprehensive media extraction - get ALL media files referenced in the slide
            media_files = self.extract_all_media_files(extract_path, target_slide_num)
            
            # Copy each referenced media file from SOURCE to OUTPUT
            src_media_dir = os.path.join(extract_path, "ppt", "media")
            dst_media_dir = os.path.join(output_path, "ppt", "media")
            if media_files and os.path.exists(src_media_dir):
                os.makedirs(dst_media_dir, exist_ok=True)
                self.log_message(f"Copying {len(media_files)} media files")
                for media_name in media_files:
                    src_media = os.path.join(src_media_dir, media_name)
                    dst_media = os.path.join(dst_media_dir, media_name)
                    if os.path.exists(src_media):
                        shutil.copy2(src_media, dst_media)
                        self.log_message(f"Copied media file: {media_name}")
                    else:
                        self.log_message(f"Warning: Media file not found: {media_name}", "WARN")
            elif media_files:
                self.log_message(f"Warning: Media directory not found: {src_media_dir}", "WARN")
            else:
                self.log_message("No media files found for this slide")
            
            # --- NOW clean slides directory (after media is copied) ---
            self.clean_slides_directory(output_path, target_slide)
            
            # Update presentation structure
            self.update_presentation_structure(output_path)
            
            # Create the final PPTX file
            with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
                for root, dirs, files in os.walk(output_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, output_path)
                        zip_ref.write(file_path, arcname)

    def get_slide_media_files(self, extract_path, slide_number):
        """
        Get media files referenced by a specific slide (simplified version for merging).
        """
        media_files = set()
        
        # Check slide relationships file
        slides_rels_dir = os.path.join(extract_path, "ppt", "slides", "_rels")
        rels_file = os.path.join(slides_rels_dir, f'slide{slide_number}.xml.rels')
        
        if os.path.exists(rels_file):
            try:
                tree = ET.parse(rels_file)
                root = tree.getroot()
                for rel in root.findall('.//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'):
                    target = rel.get('Target')
                    if target and (target.startswith('../media/') or target.startswith('media/')):
                        media_name = os.path.basename(target)
                        media_files.add(media_name)
            except Exception as e:
                self.log_message(f"Error parsing slide relationships: {e}", "WARN")
        
        return media_files

    def update_slide_media_references(self, slides_dir, slide_num, old_media_name, new_media_name):
        """
        Update the slide's relationship file to reference the new media file name.
        """
        try:
            rels_file = os.path.join(slides_dir, "_rels", f"slide{slide_num}.xml.rels")
            if os.path.exists(rels_file):
                tree = ET.parse(rels_file)
                root = tree.getroot()
                
                for rel in root.findall('.//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'):
                    target = rel.get('Target')
                    if target and os.path.basename(target) == old_media_name:
                        # Update the target to reference the new media file name
                        new_target = target.replace(old_media_name, new_media_name)
                        rel.set('Target', new_target)
                        self.log_message(f"Updated media reference: {old_media_name} -> {new_media_name}")
                
                tree.write(rels_file, encoding='utf-8', xml_declaration=True)
        except Exception as e:
            self.log_message(f"Error updating slide media references: {e}", "WARN")

    def extract_all_media_files(self, extract_path, slide_number):
        """
        Extract ONLY media files referenced by the specific slide.
        This prevents images from other slides from being included.
        """
        media_files = set()
        
        # 1. Check slide relationships file - this is the most important source
        slides_rels_dir = os.path.join(extract_path, "ppt", "slides", "_rels")
        rels_file = os.path.join(slides_rels_dir, f'slide{slide_number}.xml.rels')
        
        if os.path.exists(rels_file):
            try:
                tree = ET.parse(rels_file)
                root = tree.getroot()
                for rel in root.findall('.//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'):
                    target = rel.get('Target')
                    rel_type = rel.get('Type')
                    
                    # Only include media files that are directly referenced
                    if target and (target.startswith('../media/') or target.startswith('media/')):
                        media_name = os.path.basename(target)
                        media_files.add(media_name)
                        self.log_message(f"Found media in slide relationships: {media_name}")
            except Exception as e:
                self.log_message(f"Error parsing slide relationships: {e}", "WARN")
        
        # 2. Check the slide XML file itself for embedded media references
        slides_dir = os.path.join(extract_path, "ppt", "slides")
        slide_file = os.path.join(slides_dir, f'slide{slide_number}.xml')
        
        if os.path.exists(slide_file):
            try:
                tree = ET.parse(slide_file)
                root = tree.getroot()
                
                # Look for all possible media references in the slide
                namespaces = {
                    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
                    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
                    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
                    'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
                    'dgm': 'http://schemas.openxmlformats.org/drawingml/2006/diagram',
                    'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart'
                }
                
                # Look for picture references
                for pic in root.findall('.//pic:pic', namespaces):
                    blip = pic.find('.//a:blip', namespaces)
                    if blip is not None:
                        embed = blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                        link = blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}link')
                        if embed or link:
                            self.log_message(f"Found embedded picture reference: {embed or link}")
                
                # Look for shape references that might contain images
                for shape in root.findall('.//p:sp', namespaces):
                    blip = shape.find('.//a:blip', namespaces)
                    if blip is not None:
                        embed = blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                        link = blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}link')
                        if embed or link:
                            self.log_message(f"Found shape with image reference: {embed or link}")
                
                # Look for any r:embed or r:link attributes (general media references)
                for elem in root.findall('.//*[@r:embed]', namespaces):
                    embed_id = elem.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                    if embed_id:
                        self.log_message(f"Found embedded object reference: {embed_id}")
                
                for elem in root.findall('.//*[@r:link]', namespaces):
                    link_id = elem.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}link')
                    if link_id:
                        self.log_message(f"Found linked object reference: {link_id}")
                
            except Exception as e:
                self.log_message(f"Error parsing slide XML: {e}", "WARN")
        
        # 3. Check slide master relationships if the slide references a master
        slides_dir = os.path.join(extract_path, "ppt", "slides")
        slide_file = os.path.join(slides_dir, f'slide{slide_number}.xml')
        
        if os.path.exists(slide_file):
            try:
                tree = ET.parse(slide_file)
                root = tree.getroot()
                namespaces = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main'}
                
                # Check if slide references a master
                sldLayoutId = root.find('.//p:sldLayoutId', namespaces)
                if sldLayoutId is not None:
                    master_id = sldLayoutId.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                    if master_id:
                        # Find the master relationship and get its media files
                        pres_rels_file = os.path.join(extract_path, "ppt", "_rels", "presentation.xml.rels")
                        if os.path.exists(pres_rels_file):
                            pres_tree = ET.parse(pres_rels_file)
                            pres_root = pres_tree.getroot()
                            for rel in pres_root.findall('.//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'):
                                if rel.get('Id') == master_id:
                                    master_target = rel.get('Target')
                                    if master_target:
                                        # Get master media files (but be careful not to include too many)
                                        master_rels_file = os.path.join(extract_path, "ppt", "slideMasters", "_rels", os.path.basename(master_target) + ".rels")
                                        if os.path.exists(master_rels_file):
                                            master_tree = ET.parse(master_rels_file)
                                            master_root = master_tree.getroot()
                                            for master_rel in master_root.findall('.//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'):
                                                master_target = master_rel.get('Target')
                                                if master_target and (master_target.startswith('../media/') or master_target.startswith('media/')):
                                                    media_name = os.path.basename(master_target)
                                                    media_files.add(media_name)
                                                    self.log_message(f"Found media in slide master: {media_name}")
                                    break
            except Exception as e:
                self.log_message(f"Error checking slide master: {e}", "WARN")
        
        # 4. ONLY include media files that we actually found references to
        # DO NOT include all media files from the directory
        media_dir = os.path.join(extract_path, "ppt", "media")
        if os.path.exists(media_dir):
            actual_media_files = set(os.listdir(media_dir))
            self.log_message(f"Found {len(media_files)} media references, {len(actual_media_files)} total media files in directory")
            
            # Only copy the media files we actually found references to
            if media_files:
                self.log_message(f"Will copy only {len(media_files)} referenced media files")
            else:
                self.log_message("No media files referenced by this slide")
        
        return media_files

    def copy_complete_structure(self, extract_path, output_path):
        shutil.copytree(extract_path, output_path, dirs_exist_ok=True)

    def clean_slides_directory(self, output_path, target_slide):
        slides_dir = os.path.join(output_path, "ppt", "slides")
        slides_rels_dir = os.path.join(output_path, "ppt", "slides", "_rels")
        target_slide_num = re.search(r'slide(\d+)\.xml', target_slide).group(1)
        for file in os.listdir(slides_dir):
            if file.startswith('slide') and file.endswith('.xml') and file != target_slide:
                os.remove(os.path.join(slides_dir, file))
        if os.path.exists(slides_rels_dir):
            for file in os.listdir(slides_rels_dir):
                if file.startswith('slide') and file.endswith('.xml.rels'):
                    slide_num = re.search(r'slide(\d+)\.xml\.rels', file).group(1)
                    if slide_num != target_slide_num:
                        os.remove(os.path.join(slides_rels_dir, file))
        if target_slide != 'slide1.xml':
            old_slide_path = os.path.join(slides_dir, target_slide)
            new_slide_path = os.path.join(slides_dir, 'slide1.xml')
            os.rename(old_slide_path, new_slide_path)
            old_rel_path = os.path.join(slides_rels_dir, f'slide{target_slide_num}.xml.rels')
            new_rel_path = os.path.join(slides_rels_dir, 'slide1.xml.rels')
            if os.path.exists(old_rel_path):
                os.rename(old_rel_path, new_rel_path)

    def update_presentation_structure(self, output_path):
        pres_file = os.path.join(output_path, "ppt", "presentation.xml")
        if os.path.exists(pres_file):
            with open(pres_file, 'r', encoding='utf-8') as f:
                content = f.read()
            ET.register_namespace('', 'http://schemas.openxmlformats.org/presentationml/2006/main')
            ET.register_namespace('a', 'http://schemas.openxmlformats.org/drawingml/2006/main')
            ET.register_namespace('r', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')
            tree = ET.parse(pres_file)
            root = tree.getroot()
            ns = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
                  'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
            slide_id_list = root.find('.//p:sldIdLst', ns)
            if slide_id_list is not None:
                slide_id_list.clear()
                slide_id = ET.SubElement(slide_id_list, '{http://schemas.openxmlformats.org/presentationml/2006/main}sldId')
                slide_id.set('id', '256')
                slide_id.set('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id', 'rId2')
            tree.write(pres_file, encoding='utf-8', xml_declaration=True)
        pres_rels_file = os.path.join(output_path, "ppt", "_rels", "presentation.xml.rels")
        if os.path.exists(pres_rels_file):
            tree = ET.parse(pres_rels_file)
            root = tree.getroot()
            relationships_to_remove = []
            for rel in root.findall('.//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'):
                if rel.get('Type') == 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide':
                    relationships_to_remove.append(rel)
            for rel in relationships_to_remove:
                root.remove(rel)
            new_rel = ET.SubElement(root, '{http://schemas.openxmlformats.org/package/2006/relationships}Relationship')
            new_rel.set('Id', 'rId2')
            new_rel.set('Type', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide')
            new_rel.set('Target', 'slides/slide1.xml')
            tree.write(pres_rels_file, encoding='utf-8', xml_declaration=True)
        app_file = os.path.join(output_path, "docProps", "app.xml")
        if os.path.exists(app_file):
            tree = ET.parse(app_file)
            root = tree.getroot()
            slides_elem = root.find('.//{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}Slides')
            if slides_elem is not None:
                slides_elem.text = '1'
            pages_elem = root.find('.//{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}Pages')
            if pages_elem is not None:
                pages_elem.text = '1'
            tree.write(app_file, encoding='utf-8', xml_declaration=True)
        content_types_file = os.path.join(output_path, "[Content_Types].xml")
        if os.path.exists(content_types_file):
            tree = ET.parse(content_types_file)
            root = tree.getroot()
            overrides_to_remove = []
            for override in root.findall('.//{http://schemas.openxmlformats.org/package/2006/content-types}Override'):
                part_name = override.get('PartName')
                if part_name and '/slides/slide' in part_name and not part_name.endswith('/slides/slide1.xml'):
                    overrides_to_remove.append(override)
            for override in overrides_to_remove:
                root.remove(override)
            tree.write(content_types_file, encoding='utf-8', xml_declaration=True)

    def merge_single_slide_presentations(self, pptx_files, output_file):
        """
        Merge multiple single-slide PPTX files into one multi-slide PPTX.
        Each slide maintains its original theme, layout, and styling.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            # Unzip all single-slide pptx files
            extracted_dirs = []
            for idx, pptx in enumerate(pptx_files):
                extract_path = os.path.join(temp_dir, f"pptx_{idx}")
                with zipfile.ZipFile(pptx, 'r') as zip_ref:
                    zip_ref.extractall(extract_path)
                extracted_dirs.append(extract_path)
            
            # Create a new base directory instead of using the first one
            base_dir = os.path.join(temp_dir, "merged_presentation")
            os.makedirs(base_dir, exist_ok=True)
            
            # Copy the complete structure from the first presentation as a starting point
            if extracted_dirs:
                shutil.copytree(extracted_dirs[0], base_dir, dirs_exist_ok=True)
            
            slides_dir = os.path.join(base_dir, "ppt", "slides")
            slides_rels_dir = os.path.join(base_dir, "ppt", "slides", "_rels")
            media_dir = os.path.join(base_dir, "ppt", "media")
            
            # Ensure directories exist
            os.makedirs(slides_dir, exist_ok=True)
            os.makedirs(slides_rels_dir, exist_ok=True)
            os.makedirs(media_dir, exist_ok=True)
            
            # Start slide numbering from 1
            slide_num = 1
            
            for idx, extract_path in enumerate(extracted_dirs):
                # Copy slide1.xml and its relationships from each presentation
                src_slide = os.path.join(extract_path, "ppt", "slides", "slide1.xml")
                dst_slide = os.path.join(slides_dir, f"slide{slide_num}.xml")
                
                if os.path.exists(src_slide):
                    shutil.copy2(src_slide, dst_slide)
                    self.log_message(f"Copied slide {slide_num} from presentation {idx+1}")
                
                # Copy slide relationships
                src_rel = os.path.join(extract_path, "ppt", "slides", "_rels", "slide1.xml.rels")
                dst_rel = os.path.join(slides_rels_dir, f"slide{slide_num}.xml.rels")
                if os.path.exists(src_rel):
                    shutil.copy2(src_rel, dst_rel)
                    self.log_message(f"Copied slide {slide_num} relationships")
                
                # Copy media files from this presentation
                src_media = os.path.join(extract_path, "ppt", "media")
                if os.path.exists(src_media):
                    # Only copy media files that are actually referenced by this specific slide
                    slide_media_files = self.get_slide_media_files(extract_path, 1)  # slide1.xml in single-slide PPTX
                    
                    for media_file in slide_media_files:
                        src_media_file = os.path.join(src_media, media_file)
                        dst_media_file = os.path.join(media_dir, media_file)
                        if os.path.exists(src_media_file):
                            # Use unique naming to avoid conflicts
                            base_name, ext = os.path.splitext(media_file)
                            unique_name = f"{base_name}_slide{slide_num}{ext}"
                            dst_media_file = os.path.join(media_dir, unique_name)
                            
                            shutil.copy2(src_media_file, dst_media_file)
                            self.log_message(f"Copied media file for slide {slide_num}: {media_file} -> {unique_name}")
                            
                            # Update the slide's relationship file to reference the new media file name
                            self.update_slide_media_references(slides_dir, slide_num, media_file, unique_name)
                
                # Copy slide masters and layouts if they don't exist
                src_slide_masters = os.path.join(extract_path, "ppt", "slideMasters")
                dst_slide_masters = os.path.join(base_dir, "ppt", "slideMasters")
                if os.path.exists(src_slide_masters) and not os.path.exists(dst_slide_masters):
                    shutil.copytree(src_slide_masters, dst_slide_masters)
                    self.log_message(f"Copied slide masters from presentation {idx+1}")
                
                src_slide_layouts = os.path.join(extract_path, "ppt", "slideLayouts")
                dst_slide_layouts = os.path.join(base_dir, "ppt", "slideLayouts")
                if os.path.exists(src_slide_layouts) and not os.path.exists(dst_slide_layouts):
                    shutil.copytree(src_slide_layouts, dst_slide_layouts)
                    self.log_message(f"Copied slide layouts from presentation {idx+1}")
                
                # Copy themes if they don't exist
                src_themes = os.path.join(extract_path, "ppt", "theme")
                dst_themes = os.path.join(base_dir, "ppt", "theme")
                if os.path.exists(src_themes) and not os.path.exists(dst_themes):
                    shutil.copytree(src_themes, dst_themes)
                    self.log_message(f"Copied themes from presentation {idx+1}")
                
                slide_num += 1
            
            # Update presentation structure for the correct number of slides
            self.update_merged_presentation_structure(base_dir, slide_num - 1)
            
            # Zip up the base_dir as output_file
            with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
                for root, dirs, files in os.walk(base_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, base_dir)
                        zip_ref.write(file_path, arcname)

    def update_merged_presentation_structure(self, base_dir, num_slides):
        pres_file = os.path.join(base_dir, "ppt", "presentation.xml")
        if os.path.exists(pres_file):
            tree = ET.parse(pres_file)
            root = tree.getroot()
            ns = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
                  'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
            slide_id_list = root.find('.//p:sldIdLst', ns)
            if slide_id_list is not None:
                slide_id_list.clear()
                for i in range(num_slides):
                    slide_id = ET.SubElement(slide_id_list, '{http://schemas.openxmlformats.org/presentationml/2006/main}sldId')
                    slide_id.set('id', str(256 + i))
                    slide_id.set('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id', f'rId{i+2}')
            tree.write(pres_file, encoding='utf-8', xml_declaration=True)
        pres_rels_file = os.path.join(base_dir, "ppt", "_rels", "presentation.xml.rels")
        if os.path.exists(pres_rels_file):
            tree = ET.parse(pres_rels_file)
            root = tree.getroot()
            # Remove all slide relationships
            relationships_to_remove = []
            for rel in root.findall('.//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'):
                if rel.get('Type') == 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide':
                    relationships_to_remove.append(rel)
            for rel in relationships_to_remove:
                root.remove(rel)
            # Add slide relationships
            for i in range(num_slides):
                new_rel = ET.SubElement(root, '{http://schemas.openxmlformats.org/package/2006/relationships}Relationship')
                new_rel.set('Id', f'rId{i+2}')
                new_rel.set('Type', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide')
                new_rel.set('Target', f'slides/slide{i+1}.xml')
            tree.write(pres_rels_file, encoding='utf-8', xml_declaration=True)
        content_types_file = os.path.join(base_dir, "[Content_Types].xml")
        if os.path.exists(content_types_file):
            tree = ET.parse(content_types_file)
            root = tree.getroot()
            overrides_to_remove = []
            for override in root.findall('.//{http://schemas.openxmlformats.org/package/2006/content-types}Override'):
                part_name = override.get('PartName')
                if part_name and '/slides/slide' in part_name:
                    overrides_to_remove.append(override)
            for override in overrides_to_remove:
                root.remove(override)
            for i in range(num_slides):
                new_override = ET.SubElement(root, '{http://schemas.openxmlformats.org/package/2006/content-types}Override')
                new_override.set('PartName', f'/ppt/slides/slide{i+1}.xml')
                new_override.set('ContentType', 'application/vnd.openxmlformats-officedocument.presentationml.slide+xml')
            tree.write(content_types_file, encoding='utf-8', xml_declaration=True)

    def flatten_slide_numbers(self, slide_numbers):
        """Flatten slide_numbers to a flat list of integers."""
        flat = []
        if isinstance(slide_numbers, list):
            for s in slide_numbers:
                if isinstance(s, list):
                    flat.extend(self.flatten_slide_numbers(s))
                else:
                    flat.append(s)
        elif slide_numbers is not None:
            flat = [slide_numbers]
        return flat

    def process_nifi_input(self, input_json: str) -> str:
        """
        Process JSON input from NiFi and return the path to generated PPT file
        """
        # Parse input JSON
        try:
            data = json.loads(input_json)
            self.log_message(f"Successfully parsed JSON input with {len(str(data))} characters")
        except Exception as e:
            self.log_message(f"Failed to parse input JSON: {e}", "ERROR")
            raise Exception(f"Failed to parse input JSON: {e}")
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("extracted_items", [])
        else:
            items = []
        self.log_message(f"Found {len(items)} items to process")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Always prepend these 5 slides from BuyProperly.pptx
        initial_slides_obj = {
            "slide_number": [[1, 2, 3, 4, 5]],
            "source_file": "BuyProperly.pptx",
            "link": "https://shorthillstech-my.sharepoint.com/personal/rakhee_prajapat_shorthills_ai/_layouts/15/Doc.aspx?sourcedoc=%7B504CAE2B-2241-4F15-B43D-990B21517DA4%7D&file=BuyProperly.pptx&action=edit&mobileredirect=true",
            "content_summary": "Integration of human-in-the-loop approach for compliance validation and continuous updates to knowledge base."
        }
        items = [initial_slides_obj] + items

        # For NiFi mode, create output in temp directory, not current directory
        output_filename = f"nifi_processed_presentation_{timestamp}.pptx"
        output_path = os.path.join(self.temp_dir, output_filename)
        
        if not self.get_access_token():
            raise Exception("Failed to get access token")
        # --- Remove initial_template_path feature: process JSON objects in order ---
        # Only process JSON-specified slides as single-slide PPTX files and merge them
        json_slide_pptx_files = []
        downloaded_files_to_cleanup = []  # Track downloaded files for cleanup
        
        for i, item in enumerate(items):
            try:
                source_file = item.get("source_file", "")
                slide_numbers = item.get("slide_number")
                link = item.get("link", "")
                content_summary = item.get("content_summary", "")
                self.log_message(f"Processing item {i+1}/{len(items)}: {source_file}")
                if not source_file.lower().endswith('.pptx'):
                    self.log_message(f"Skipping {source_file} (not a PPTX file)", "WARN")
                    continue
                if slide_numbers is None:
                    self.log_message(f"Skipping {source_file} (no slide numbers specified)", "WARN")
                    continue
                if not link:
                    self.log_message(f"Skipping {source_file} (no download link)", "WARN")
                    continue
                self.log_message(f"Processing {source_file} with slide numbers: {slide_numbers}")
                
                # Use get_or_download_file to handle caching
                downloaded_file_path = self.get_or_download_file(source_file, link)
                if not downloaded_file_path:
                    self.log_message(f"Failed to get or download file {source_file}", "ERROR")
                    continue
                
                # Verify downloaded file exists before processing
                if not os.path.exists(downloaded_file_path):
                    self.log_message(f"Downloaded file not found: {downloaded_file_path}", "ERROR")
                    continue
                
                self.log_message(f"Downloaded file verified: {os.path.basename(downloaded_file_path)} ({os.path.getsize(downloaded_file_path)} bytes)")
                
                # Process all slides from this file before cleaning up
                slides_to_process = self.flatten_slide_numbers(slide_numbers)
                self.log_message(f"Processing {len(slides_to_process)} slides from {source_file}")
                
                # Extract the file temporarily to check for duplicates
                with tempfile.TemporaryDirectory() as temp_extract_dir:
                    with zipfile.ZipFile(downloaded_file_path, 'r') as zip_ref:
                        zip_ref.extractall(temp_extract_dir)
                    
                    for slide_number in slides_to_process:
                        # Check for duplicate slide before processing
                        if self.is_duplicate_slide(source_file, slide_number, temp_extract_dir):
                            self.log_message(f"Skipping duplicate slide: {source_file} slide {slide_number}")
                            continue
                        
                        temp_single_slide_pptx = os.path.join(self.temp_dir, f"json_slide_{i}_{slide_number}_{timestamp}.pptx")
                        self.log_message(f"Creating single slide PPTX for slide {slide_number} from {source_file}")
                        self.copy_single_slide(downloaded_file_path, temp_single_slide_pptx, slide_number)
                        json_slide_pptx_files.append(temp_single_slide_pptx)
                        self.log_message(f"Successfully created single slide PPTX: {os.path.basename(temp_single_slide_pptx)}")
                
                # Add to cleanup list instead of deleting immediately
                downloaded_files_to_cleanup.append(downloaded_file_path)
                self.log_message(f"Added {source_file} to cleanup list")
                
            except Exception as e:
                error_msg = f"Failed to process item {i+1} ({source_file}): {str(e)}"
                self.log_message(error_msg, "ERROR")
                self.log_message(f"Stack trace: {traceback.format_exc()}", "ERROR")
        
        # Clean up all downloaded files after processing is complete
        # Use set to avoid duplicate cleanup attempts
        unique_downloaded_files = set(self.file_cache.values())
        for downloaded_file_path in unique_downloaded_files:
            try:
                if os.path.exists(downloaded_file_path):
                    os.remove(downloaded_file_path)
                    self.log_message(f"Cleaned up downloaded file: {os.path.basename(downloaded_file_path)}")
                else:
                    self.log_message(f"Downloaded file already removed: {os.path.basename(downloaded_file_path)}")
            except Exception as del_err:
                self.log_message(f"Warning: Could not delete downloaded file: {del_err}", "WARN")
        
        # Clear the cache
        self.file_cache.clear()
        self.log_message("Cleared file cache")
        
        # Clear slide cache and show statistics
        total_slides_processed = len(self.slide_cache)
        self.slide_cache.clear()
        self.log_message("Cleared slide cache")
        
        # Log cache statistics
        total_items = len(items)
        unique_files = len(set(item.get("source_file", "") for item in items if item.get("source_file", "").lower().endswith('.pptx')))
        self.log_message(f"Cache statistics: Processed {total_items} items from {unique_files} unique files, {total_slides_processed} unique slides")
        
        json_slides_pptx = os.path.join(self.temp_dir, f"json_slides_{timestamp}.pptx")
        if json_slide_pptx_files:
            self.merge_single_slide_presentations(json_slide_pptx_files, json_slides_pptx)
            shutil.copy2(json_slides_pptx, output_path)
            
            # Clean up temporary slide files
            for temp_file in json_slide_pptx_files:
                try:
                    os.remove(temp_file)
                    self.log_message(f"Cleaned up temporary slide file: {os.path.basename(temp_file)}")
                except Exception as cleanup_err:
                    self.log_message(f"Warning: Could not clean up temporary slide file: {cleanup_err}", "WARN")
            
            # Clean up merged presentation file
            try:
                os.remove(json_slides_pptx)
                self.log_message(f"Cleaned up merged presentation file: {os.path.basename(json_slides_pptx)}")
            except Exception as cleanup_err:
                self.log_message(f"Warning: Could not clean up merged presentation file: {cleanup_err}", "WARN")
        else:
            raise Exception("No slides were processed successfully.")
        self.log_message(f"Final presentation ready at: {output_path}")
        
        return output_path

    def cleanup_temp_directory(self):
        """Clean up the entire temp directory and its contents"""
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                self.log_message(f"Cleaned up temp directory: {self.temp_dir}")
            else:
                self.log_message("Temp directory does not exist, nothing to clean")
        except Exception as e:
            self.log_message(f"Warning: Could not clean up temp directory: {e}", "WARN")


def main():
    """Main function for NiFi integration"""
    parser = argparse.ArgumentParser(description="NiFi PowerPoint Processor")
    parser.add_argument('--test', action='store_true', help='Run in test mode with sample data')
    parser.add_argument('--json', help='Path to JSON file for testing')
    parser.add_argument('--output', help='Output path for testing')
    args = parser.parse_args()
    
    # Configuration from environment variables
    client_id = os.getenv('AZURE_CLIENT_ID')
    client_secret = os.getenv('AZURE_CLIENT_SECRET')
    tenant_id = os.getenv('AZURE_TENANT_ID')
    nifi_temp_dir = os.getenv('NIFI_TEMP_DIR')
    
    # Debug: Print environment variable status
    print(f"DEBUG: AZURE_CLIENT_ID present: {client_id is not None}", file=sys.stderr)
    print(f"DEBUG: AZURE_CLIENT_SECRET present: {client_secret is not None}", file=sys.stderr)
    print(f"DEBUG: AZURE_TENANT_ID present: {tenant_id is not None}", file=sys.stderr)
    print(f"DEBUG: NIFI_TEMP_DIR: {nifi_temp_dir}", file=sys.stderr)
    print(f"DEBUG: System temp directory: {tempfile.gettempdir()}", file=sys.stderr)
    print(f"DEBUG: Current working directory: {os.getcwd()}", file=sys.stderr)
    print(f"DEBUG: Script location: {os.path.abspath(__file__)}", file=sys.stderr)
    
    # Validate required environment variables
    if not all([client_id, client_secret, tenant_id]):
        print("ERROR: Missing required environment variables:", file=sys.stderr)
        print("Required: AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID", file=sys.stderr)
        print(f"Available environment variables: {list(os.environ.keys())}", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Initialize processor
        processor = NiFiPPTProcessor(
            client_id=client_id,
            client_secret=client_secret,
            tenant_id=tenant_id,
            nifi_temp_dir=nifi_temp_dir
        )
        
        # Test mode
        if args.test:
            test_json = json.dumps({
                "extracted_items": [
                    {
                        "source_file": "test.pptx",
                        "slide_number": 1,
                        "link": "https://example.sharepoint.com/test.pptx",
                        "content_summary": "Test slide"
                    }
                ]
            })
            processor.log_message("Running in test mode")
            print(f"Test JSON: {test_json}")
            sys.exit(0)
        
        # Local testing with JSON file
        if args.json:
            with open(args.json, 'r', encoding='utf-8') as f:
                input_json = f.read()
            
            output_ppt_path = processor.process_nifi_input(input_json)
            
            if args.output:
                shutil.copy2(output_ppt_path, args.output)
                print(f"SUCCESS: Output saved to {args.output}")
                # Clean up the original output file since we copied it
                try:
                    os.remove(output_ppt_path)
                    print(f"Cleaned up original output file: {output_ppt_path}")
                except Exception as cleanup_err:
                    print(f"Warning: Could not clean up original output file: {cleanup_err}")
            else:
                print(f"SUCCESS: Output ready at {output_ppt_path}")
            
            sys.exit(0)
        
        # NiFi mode: Read from stdin, output to stdout
        processor.log_message("Starting NiFi processing mode")
        
        # Read JSON from stdin
        try:
            input_json = sys.stdin.read().strip()
            if not input_json:
                raise Exception("No input received from stdin")
            
            processor.log_message(f"Received {len(input_json)} characters from stdin")
            
        except Exception as e:
            print(f"ERROR: Failed to read from stdin: {e}", file=sys.stderr)
            sys.exit(1)
        
        # Process the input
        output_ppt_path = processor.process_nifi_input(input_json)
        
        # Write the PowerPoint file to stdout as binary
        processor.log_message(f"Writing output file to stdout: {output_ppt_path}")
        
        try:
            with open(output_ppt_path, 'rb') as ppt_file:
                # Write binary data to stdout
                sys.stdout.buffer.write(ppt_file.read())
                sys.stdout.buffer.flush()
            
            processor.log_message("Successfully wrote PPTX to stdout")
            
        except Exception as e:
            processor.log_message(f"Error writing to stdout: {e}", "ERROR")
            sys.exit(1)
        finally:
            # Clean up the output file after writing to stdout
            try:
                os.remove(output_ppt_path)
                processor.log_message(f"Cleaned up output file: {output_ppt_path}")
            except Exception as cleanup_err:
                processor.log_message(f"Warning: Could not clean up output file: {cleanup_err}", "WARN")
            
            # Clean up the entire temp directory after processing
            processor.cleanup_temp_directory()
        
        processor.log_message("NiFi processing completed successfully")
        
    except Exception as e:
        print(f"FATAL ERROR: {e}", file=sys.stderr)
        print(f"Stack trace: {traceback.format_exc()}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
    