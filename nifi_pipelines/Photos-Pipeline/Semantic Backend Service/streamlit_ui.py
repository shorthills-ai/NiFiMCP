import streamlit as st
import requests
import json
import os
from dotenv import load_dotenv

# --- Load environment variables ---
load_dotenv()

# Replace with the actual URL where your FastAPI backend is running
# If running locally, it might be something like "http://localhost:8000"
FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:8000")

st.set_page_config(layout="wide", page_title="Image Semantic Search")

st.title("📸 Semantic Image Search")
st.markdown("Enter a description to find visually similar images.")

# User input for the query
user_query = st.text_input("What are you looking for?", placeholder="e.g., 'a cat playing with a ball', 'sunset over mountains'")

if st.button("Search Images"):
    if not user_query:
        st.warning("Please enter a query to search.")
    else:
        with st.spinner("Searching for images..."):
            try:
                # Send the query to the FastAPI backend
                response = requests.post(
                    f"{FASTAPI_URL}/semantic-query",
                    json={"query": user_query}
                )
                response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
                
                results = response.json()

                if results and results.get("image_results"):
                    st.success(results.get("message", "Search complete."))
                    
                    image_results = results["image_results"]
                    
                    for i, img_data in enumerate(image_results):
                        image_url = img_data.get("image_url")
                        summary = img_data.get("summary")
                        
                        if image_url:
                            st.markdown(f"**Summary:** {summary}")
                            st.markdown(f"**Link:** [Open Image]({image_url})") # Clickable link
                            st.markdown("---") # Separator for clarity
                        else:
                            st.warning(f"Could not display image for: {summary} (No URL found)")
                            st.markdown(f"**Summary:** {summary}")
                            st.markdown("---")
                else:
                    st.info("No images found for your query. Try a different one!")

            except requests.exceptions.ConnectionError:
                st.error(f"Could not connect to the backend API at {FASTAPI_URL}. Please ensure it's running.")
            except requests.exceptions.Timeout:
                st.error("The request to the backend API timed out.")
            except requests.exceptions.RequestException as e:
                st.error(f"An error occurred during the API request: {e}")
            except Exception as e:
                st.error(f"An unexpected error occurred: {e}")