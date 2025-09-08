# main.py
import os
import weaviate
import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from weaviate.classes.init import Auth
from weaviate.classes.query import Filter, GeoCoordinate # GeoCoordinate is now needed!
from metadata_extractor import extract_metadata_fields
from typing import Optional, List, Dict, Any
from geopy.distance import geodesic
from contextlib import asynccontextmanager

load_dotenv()

WEAVIATE_URL = os.getenv("WEAVIATE_URL")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")

# Declare client globally but initialize within lifespan for proper management
client = None

# --- FastAPI Lifespan Context Manager ---
# This is crucial for managing the Weaviate client's lifecycle (connect on startup, close on shutdown)
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the lifecycle of the Weaviate client.
    Connects on startup and closes on shutdown.
    """
    global client
    try:
        print("Attempting to connect to Weaviate Cloud (FastAPI startup)...")
        client = weaviate.connect_to_weaviate_cloud(
            cluster_url=WEAVIATE_URL,
            auth_credentials=Auth.api_key(WEAVIATE_API_KEY),
        )
        print("✅ Connected to Weaviate Cloud (Weaviate Client v4)")
        yield # Application startup is complete, proceed with requests
    except Exception as e:
        print(f"❌ Failed to connect to Weaviate: {e}")
        # Re-raise the exception to prevent the server from starting if connection fails
        raise RuntimeError(f"Failed to connect to Weaviate at startup: {e}")
    finally:
        # This block ensures the client is closed when the FastAPI application shuts down
        if client:
            client.close()
            print("👋 Weaviate connection closed (FastAPI shutdown).")


# Initialize FastAPI app with the lifespan
# The lifespan argument is vital for managing resources like the Weaviate client.
app = FastAPI(title="Photos Metadata Search API - Phase 1", lifespan=lifespan)

class QueryInput(BaseModel):
    query: str
    
# Helper function to convert parsed datetime objects and optional time constraints to timestamp range
def get_timestamp_range_from_datetimes(
    start_dt_obj: datetime.datetime, # This is already date-parsed (and potentially start of day for ranges)
    end_dt_obj: datetime.datetime,   # This is already date-parsed (and potentially end of day for ranges)
    start_time_str: Optional[str] = None, # HH:MM format
    end_time_str: Optional[str] = None    # HH:MM format
) -> tuple[Optional[int], Optional[int]]:
    
    # Ensure input datetime objects are UTC-aware
    # dateparser should ideally return UTC-aware datetimes with settings={'RETURN_AS_TIMEZONE_AWARE': True, 'TIMEZONE': 'UTC', 'TO_TIMEZONE': 'UTC'}
    # but as a safeguard, ensure they are converted to UTC if naive.
    if start_dt_obj.tzinfo is None or start_dt_obj.tzinfo.utcoffset(start_dt_obj) is None:
        start_dt_obj = start_dt_obj.replace(tzinfo=datetime.timezone.utc)
    else:
        start_dt_obj = start_dt_obj.astimezone(datetime.timezone.utc)

    if end_dt_obj.tzinfo is None or end_dt_obj.tzinfo.utcoffset(end_dt_obj) is None:
        end_dt_obj = end_dt_obj.replace(tzinfo=datetime.timezone.utc)
    else:
        end_dt_obj = end_dt_obj.astimezone(datetime.timezone.utc)

    # Initialize current_start_dt to the beginning of the start_dt_obj's day
    current_start_dt = start_dt_obj.replace(hour=0, minute=0, second=0, microsecond=0)
    # Initialize current_end_dt to the very end of the end_dt_obj's day
    current_end_dt = end_dt_obj.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Apply specific start time if provided, overriding the 00:00:00 of current_start_dt
    if start_time_str:
        try:
            h, m = map(int, start_time_str.split(':'))
            current_start_dt = current_start_dt.replace(hour=h, minute=m, second=0, microsecond=0)
        except ValueError:
            print(f"⚠️ Invalid start_time format: {start_time_str}. Ignoring start time constraint.")
            # If start time format is bad, it's better to return an invalid range than a potentially wrong one.
            return None, None 

    # Apply specific end time if provided, overriding the 23:59:59 of current_end_dt
    if end_time_str:
        try:
            h, m = map(int, end_time_str.split(':'))
            current_end_dt = current_end_dt.replace(hour=h, minute=m, second=59, microsecond=999999)
        except ValueError:
            print(f"⚠️ Invalid end_time format: {end_time_str}. Ignoring end time constraint.")
            # If end time format is bad, it's better to return an invalid range.
            return None, None 

    # Ensure the end_dt is not before the start_dt after all adjustments
    if current_end_dt < current_start_dt:
        print(f"⚠️ Adjusted end_time ({current_end_dt}) is before start_time ({current_start_dt}). This might be due to parsing issues or an invalid query (e.g., '10 PM to 9 AM on the same day'). Returning None for timestamp range.")
        return None, None # Invalidate range

    # Convert to Unix timestamps (seconds since epoch). .timestamp() on a timezone-aware object returns UTC timestamp.
    return (int(current_start_dt.timestamp()), int(current_end_dt.timestamp()))

@app.post("/metadata-query")
async def metadata_search(input: QueryInput):
    # Ensure client is available before proceeding with a query
    global client # Access the global client variable initialized by lifespan
    if client is None:
        # If client is None here, it means lifespan failed or the app isn't fully started.
        raise HTTPException(status_code=503, detail="Weaviate client is not initialized or connected.")

    user_query = input.query.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    try:
        metadata = await extract_metadata_fields(user_query)
        print("🔍 Extracted Metadata:", metadata)

        individual_filters = []
        
        if metadata.get("title"):
            individual_filters.append(Filter.by_property("title").like(f"*{metadata['title']}*"))
        
        if metadata.get("description"):
            individual_filters.append(Filter.by_property("description").like(f"*{metadata['description']}*"))

        if metadata.get("image_path"):
            individual_filters.append(Filter.by_property("image_path").like(f"*{metadata['image_path']}*"))
        
        if metadata.get("url"):
            individual_filters.append(Filter.by_property("url").like(f"*{metadata['url']}*"))
        
        if metadata.get("basename"):
            individual_filters.append(Filter.by_property("basename").like(f"*{metadata['basename']}*"))

        if metadata.get("appName"):
            individual_filters.append(Filter.by_property("appName").like(f"*{metadata['appName']}*"))
            
        if metadata.get("deviceType"):
            individual_filters.append(Filter.by_property("deviceType").like(f"*{metadata['deviceType']}*"))
        
        if metadata.get("localFolderName"):
            individual_filters.append(Filter.by_property("localFolderName").like(f"*{metadata['localFolderName']}*"))

        if metadata.get("persons"):
            person_names_from_query = [p.strip().lower() for p in metadata["persons"].split(",") if p.strip()]
            
            # For persons, use contains_any as the property "persons" in Weaviate is likely a list of strings
            # and we want to find items where the list contains ANY of the queried names/keywords.
            if person_names_from_query:
                individual_filters.append(Filter.by_property("persons").contains_any(person_names_from_query))

        # --- Date/Time Filtering (using 'timestamp' - INT) ---
        start_date_obj = metadata.get("start_date_parsed_object")
        end_date_obj = metadata.get("end_date_parsed_object")
        start_time_str = metadata.get("start_time")
        end_time_str = metadata.get("end_time")

        if start_date_obj and end_date_obj: # Ensure both start and end date objects are present
            start_ts, end_ts = get_timestamp_range_from_datetimes(
                start_date_obj,
                end_date_obj,
                start_time_str,
                end_time_str
            )
            if start_ts is not None and end_ts is not None:
                date_filter = Filter.by_property("timestamp").greater_or_equal(start_ts) \
                            & Filter.by_property("timestamp").less_or_equal(end_ts)
                individual_filters.append(date_filter)
            else:
                print("Skipping date filter due to invalid time range or parsing issues.")
        
        # --- Location-based filtering (using 'geo_location' - GEO_COORDINATE) ---
        if metadata.get("latitude") is not None and metadata.get("longitude") is not None:
            lat = metadata["latitude"]
            lon = metadata["longitude"]
            radius_km = metadata.get("radius_km", 5000)

            # Weaviate's within_geo_range expects meters
            distance_meters = radius_km * 1000 
            
            individual_filters.append(
                Filter.by_property("geo_location").within_geo_range(
                    GeoCoordinate(latitude=lat, longitude=lon),
                    distance=distance_meters
                )
            )

        if not individual_filters:
            return {"matched_images": [], "message": "No specific filters could be extracted from your query."}

        # --- Combining Filters ---
        final_filter = Filter.all_of(individual_filters)

        print("🔍 Final Filter:", final_filter)

        collection = client.collections.get("image_search")
        
        response = collection.query.fetch_objects(
            filters=final_filter,
            limit=10, 
            return_properties=[
                "title", "summary", "url", "image_path", "persons",
                "timestamp", "formatted_time", "geo_location", "altitude",
                "appName", "deviceType", "localFolderName", "basename", "description", "imageViews"
            ]
        )

        results = []
        for obj in response.objects:
            props = obj.properties
            results.append({
                "title": props.get("title"),
                "summary": props.get("summary"),
                "image_path": props.get("image_path"),
                "url": props.get("url"),
                "persons": props.get("persons", []),
                "timestamp": props.get("timestamp"),
                "formatted_time": props.get("formatted_time"),
                "geo_location": props.get("geo_location"),
                "altitude": props.get("altitude"),
                "appName": props.get("appName"),
                "deviceType": props.get("deviceType"),
                "localFolderName": props.get("localFolderName"),
                "basename": props.get("basename"),
                "description": props.get("description"),
                "imageViews": props.get("imageViews"),
            })

        # Post-fetching sorting by proximity for display if location was queried
        if metadata.get("latitude") is not None and metadata.get("longitude") is not None and results:
            query_point = (metadata["latitude"], metadata["longitude"])
            
            for item in results:
                if item.get("geo_location"):
                    item_point = (item["geo_location"].latitude, item["geo_location"].longitude) # Access object attributes
                    item["distance_km"] = geodesic(query_point, item_point).km
                else:
                    item["distance_km"] = float('inf')

            results.sort(key=lambda x: x["distance_km"])
            
            for item in results:
                if item.get("distance_km") != float('inf'):
                    item["distance_from_query_km"] = round(item["distance_km"], 2)
                else:
                    item["distance_from_query_km"] = "N/A"
                del item["distance_km"]


        return {
            "query": user_query,
            "matched_images": results,
            "message": f"Found {len(results)} matching images."
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")