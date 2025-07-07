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
client = weaviate.connect_to_weaviate_cloud(
    cluster_url=WEAVIATE_URL,
    auth_credentials=Auth.api_key(WEAVIATE_API_KEY),
)
print("✅ Connected to Weaviate Cloud")

# --- Delete class if exists ---
try:
    client.collections.delete(CLASS_NAME)
    print(f"🗑️ Deleted class '{CLASS_NAME}' (if it existed)")
except Exception as e:
    print(f"⚠️ Could not delete class: {e}")

# --- Create collection with enum-style Vectorizer ---
try:
    client.collections.create(
        name=CLASS_NAME,
        # For no Weaviate-side vectorization (you provide vectors),
        # you can either omit vectorizer_config or set it to None.
        # If you want to explicitly use a module but disable its vectorizer
        # for the collection, you would use module_config.
        # In most cases, if you're providing your own vectors, simply omitting
        # vectorizer_config or setting it to None is the way.
        vectorizer_config=None, # This signifies no Weaviate-side vectorization
        properties=[
            Property(name="image_path", data_type=DataType.TEXT, tokenization=Tokenization.WHITESPACE),
            Property(name="summary", data_type=DataType.TEXT, tokenization=Tokenization.WORD),
            Property(name="title", data_type=DataType.TEXT, tokenization=Tokenization.WHITESPACE),
            Property(name="description", data_type=DataType.TEXT, tokenization=Tokenization.WORD),
            Property(name="imageViews", data_type=DataType.INT),
            Property(name="timestamp", data_type=DataType.INT),
            Property(name="formatted_time", data_type=DataType.TEXT, tokenization=Tokenization.FIELD),
            Property(name="url", data_type=DataType.TEXT, tokenization=Tokenization.WHITESPACE),
            Property(name="latitude", data_type=DataType.NUMBER),
            Property(name="longitude", data_type=DataType.NUMBER),
            Property(name="altitude", data_type=DataType.NUMBER),
            Property(name="appName", data_type=DataType.TEXT, tokenization=Tokenization.WHITESPACE),
            Property(name="deviceType", data_type=DataType.TEXT, tokenization=Tokenization.FIELD),
            Property(name="localFolderName", data_type=DataType.TEXT, tokenization=Tokenization.FIELD),
            Property(name="persons", data_type=DataType.TEXT_ARRAY, tokenization=Tokenization.WORD),
            Property(name="basename", data_type=DataType.TEXT, tokenization=Tokenization.WORD),
        ]
    )
    print(f"✅ Created class '{CLASS_NAME}' with all properties and no Weaviate-side vectorizer.")
except Exception as e:
    print(f"❌ Failed to create class: {e}")

# --- Close connection ---
client.close()
print("Connection closed.")