# Schema creation script for Weaviate Cloud
import os
from dotenv import load_dotenv
import weaviate
from weaviate.classes.init import Auth
from weaviate.classes.config import Property, DataType, Tokenization, Reconfigure

# --- Load env vars ---
load_dotenv()
WEAVIATE_URL = os.getenv("WEAVIATE_URL")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")
CLASS_NAME = "image_search"

# --- Connect to Weaviate Cloud ---
try:
    client = weaviate.connect_to_weaviate_cloud(
        cluster_url=WEAVIATE_URL,
        auth_credentials=Auth.api_key(WEAVIATE_API_KEY),
    )
    print("✅ Connected to Weaviate Cloud")
except Exception as e:
    print(f"❌ Failed to connect to Weaviate: {e}")
    raise RuntimeError(f"Failed to connect to Weaviate: {e}")

# --- Delete class if exists ---
try:
    client.collections.delete(CLASS_NAME)
    print(f"🗑️ Deleted existing class '{CLASS_NAME}'")
except weaviate.exceptions.WeaviateGRPCError as e:
    if "not found" in str(e):
        print(f"ℹ️ Class '{CLASS_NAME}' did not exist, no deletion needed.")
    else:
        print(f"⚠️ Could not delete class (unexpected error): {e}")
except Exception as e:
    print(f"⚠️ Could not delete class (general error): {e}")

# --- Create collection with enhanced properties ---
try:
    client.collections.create(
        name=CLASS_NAME,
        vectorizer_config=None, # You're providing vectors client-side
        properties=[
            Property(name="image_path", data_type=DataType.TEXT, tokenization=Tokenization.WHITESPACE),
            Property(name="summary", data_type=DataType.TEXT, tokenization=Tokenization.WORD),
            Property(name="title", data_type=DataType.TEXT, tokenization=Tokenization.WORD),
            Property(name="description", data_type=DataType.TEXT, tokenization=Tokenization.WORD),
            Property(name="imageViews", data_type=DataType.INT),
            Property(name="timestamp", data_type=DataType.INT),
            Property(name="formatted_time", data_type=DataType.TEXT, tokenization=Tokenization.FIELD),
            Property(name="url", data_type=DataType.TEXT, tokenization=Tokenization.WHITESPACE),
            
            # --- THE CRITICAL FIX IS HERE ---
            Property(name="geo_location", data_type=DataType.GEO_COORDINATES), 
            # Altitude remains a separate NUMBER property
            Property(name="altitude", data_type=DataType.NUMBER), 

            Property(name="appName", data_type=DataType.TEXT, tokenization=Tokenization.WHITESPACE),
            Property(name="deviceType", data_type=DataType.TEXT, tokenization=Tokenization.WORD),
            Property(name="localFolderName", data_type=DataType.TEXT, tokenization=Tokenization.WORD),
            Property(name="persons", data_type=DataType.TEXT_ARRAY, tokenization=Tokenization.WORD), # Changed to WORD for flexible person search
            Property(name="basename", data_type=DataType.TEXT, tokenization=Tokenization.WORD),
        ]
    )
    print(f"✅ Created class '{CLASS_NAME}' with all properties and no Weaviate-side vectorizer.")
except Exception as e:
    print(f"❌ Failed to create class: {e}")

# --- Close connection ---
client.close()
print("Connection closed.")