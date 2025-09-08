import streamlit as st
import requests
import os
from dotenv import load_dotenv

# --- Load environment variables ---
load_dotenv()

# Replace with the actual URL where your FastAPI backend is running
FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:8000")

st.set_page_config(layout="wide", page_title="🔎 Metadata Image Search")
st.title("📷 Metadata-Based Search")
st.markdown("Enter a natural language query to search image metadata (e.g., title, person, path, url).")

query = st.text_input("Enter your query:", placeholder="e.g., show images of rohit sharma from the match in Delhi", key="metadata_query")

if st.button("Search Images by Metadata", key="search_button"):
    if not query.strip():
        st.warning("Please enter a query to search.")
    else:
        with st.spinner("Querying FastAPI backend for metadata..."):
            try:
                response = requests.post(
                    f"{FASTAPI_URL}/metadata-query",
                    json={"query": query.strip()}
                )
                response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
                
                results = response.json()

                matched_images = results.get("matched_images", [])
                
                if not matched_images:
                    st.info(results.get("message", "No matching images found for your query."))
                else:
                    st.success(f"🔍 Found {len(matched_images)} matching images.")
                    
                    # Define number of columns for display
                    num_columns = 3 # Adjust as needed
                    
                    # Create a list of columns
                    cols = st.columns(num_columns)
                    
                    for idx, img_data in enumerate(matched_images):
                        col = cols[idx % num_columns] # Cycle through columns
                        
                        with col: # Everything inside this 'with' block will be in the current column
                            st.markdown(f"**Result {idx+1}**") # Optional: Result number
                            
                            title = img_data.get('title', 'N/A')
                            summary = img_data.get('summary', 'No summary')
                            image_path = img_data.get('image_path', '')
                            image_url = img_data.get("url")
                            
                            # Display image if URL is available
                            # if image_url:
                            #     st.image(image_url, caption=f"Title: {title}", use_container_width=True)
                            # else:
                            #     st.image("https://via.placeholder.com/150?text=No+Image", caption=f"No URL for: {title}", use_container_width=True)
                            
                            st.markdown(f"**Summary:** {summary}")
                            if image_url:
                                st.markdown(f"**Link:** [Open Image]({image_url})") # Clickable link
                            st.markdown(f"**Path:** `{image_path}`")
                            st.markdown("---") # Separator within each column

            except requests.exceptions.ConnectionError:
                st.error(f"❌ Could not connect to the backend API at {FASTAPI_URL}. Please ensure it's running.")
            except requests.exceptions.Timeout:
                st.error("❌ The request to the backend API timed out.")
            except requests.exceptions.RequestException as e:
                st.error(f"❌ An error occurred during the API request: {e}")
            except Exception as e:
                st.error(f"❌ An unexpected error occurred: {e}")

st.markdown("---")