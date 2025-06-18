import os
import boto3
import logging
from pathlib import Path
from dotenv import load_dotenv
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# S3 config
S3_BUCKET = os.getenv("AWS_S3_BUCKET_NAME")
S3_PREFIX = os.getenv("AWS_S3_PREFIX", "qti_packages/")

def download_qti_files(output_dir: str = "downloaded_qti_files"):
    """
    Download all QTI zip files from the specified S3 bucket and prefix.
    
    Args:
        output_dir (str): Directory where files will be downloaded
    """
    if not S3_BUCKET:
        raise ValueError("AWS_S3_BUCKET_NAME environment variable is not set")
        
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    
    if not aws_access_key or not aws_secret_key:
        raise ValueError("AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables must be set")
    
    # Initialize S3 client
    s3 = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key
    )
    
    # Create output directory if it doesn't exist
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    try:
        # List all objects in the bucket with the specified prefix
        logger.info(f"Listing objects in bucket {S3_BUCKET} with prefix {S3_PREFIX}")
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX)
        
        total_files = 0
        downloaded_files = 0
        
        # Iterate through all pages of results
        for page in pages:
            if 'Contents' not in page:
                continue
                
            for obj in page['Contents']:
                key = obj['Key']
                if not key.endswith('.zip'):
                    continue
                    
                total_files += 1
                file_name = Path(key).name
                local_path = output_path / file_name
                
                logger.info(f"Downloading {key} to {local_path}")
                try:
                    s3.download_file(S3_BUCKET, key, str(local_path))
                    downloaded_files += 1
                    logger.info(f"Successfully downloaded {file_name}")
                except ClientError as e:
                    logger.error(f"Error downloading {key}: {str(e)}")
        
        logger.info(f"Download complete. Downloaded {downloaded_files} out of {total_files} files.")
        
    except ClientError as e:
        logger.error(f"Error accessing S3: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        download_qti_files()
    except Exception as e:
        logger.error(f"Error in main process: {str(e)}")
        raise 