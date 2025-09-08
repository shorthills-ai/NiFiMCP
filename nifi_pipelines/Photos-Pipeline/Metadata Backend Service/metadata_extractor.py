# metadata_extractor.py (Updated with refined date range parsing)

import os
import json
import re
import datetime
from dateparser import parse
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

# --- Azure OpenAI Client Setup ---
client_openai = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version="2024-02-01",
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
)

DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")

# --- Geopy Nominatim Setup ---
geolocator = Nominatim(user_agent="ImageSearchApp_YourCompanyName_v1")

async def extract_metadata_fields(query: str) -> dict:
    llm_schema = {
        "title": "name or partial name of the image (e.g., 'vacation photos')",
        "persons": "names of people clearly identified in the image, comma-separated (e.g., 'rohit sharma, Brad pitt, Alicia'). Extract only the names, do not add prefixes like 'name'. If a single word can be a person's name, prioritize 'persons' over 'title'.",
        "image_path": "full or partial file path of the image (e.g., '/users/my_pics/holiday')",
        "url": "URL or partial URL of the image if mentioned (e.g., 'example.com/images/')",
        "basename": "file name without extension (e.g., 'image_001' from 'image_001.jpg')",
        "appName": "name of the application where the photo was viewed or created (e.g., 'Google Photos', 'Lightroom')",
        "deviceType": "type of device (e.g., 'android', 'iphone', 'canon camera')",
        "localFolderName": "name of the local folder (e.g., 'My Pictures', 'Vacation 2024')",
        "date_query": "specific single date mentioned (e.g., 'June 23rd 2023', 'yesterday', 'last week', 'Christmas'). Do not include time constraints or date ranges in this field. Only populate this if a specific day is mentioned or a single year.",
        "date_range_start": "start date of a date range (e.g., 'June 1st 2023' from 'photos from June 1st to June 15th'). Only populate if an explicit date range is given. Do not include time.",
        "date_range_end": "end date of a date range (e.g., 'June 15th 2023' from 'photos from June 1st to June 15th'). Only populate if an explicit date range is given. Do not include time.",
        "start_time": "earliest time constraint (e.g., '9 AM', '14:00', 'morning'). Convert to HH:MM (24-hour format) if possible. Can be used with or without a specific date.",
        "end_time": "latest time constraint (e.g., '5 PM', '17:00', 'evening'). Convert to HH:MM (24-hour format) if possible. Can be used with or without a specific date.",
        "location_query": "name of a specific location, landmark, city, stadium, or park (e.g., 'Eiffel Tower', 'Melbourne Cricket Ground', 'New York City'). Prioritize specific place names over general regions like states or countries. Do not include latitude/longitude numbers in this field."
    }

    prompt = f"""
You are an intelligent assistant that extracts relevant metadata filters from user queries about photos.

Your task is to identify and extract values for the following fields based on the user's query.

If a field is not explicitly mentioned or clearly implied, DO NOT include it in the output JSON.

Schema and Examples:

{json.dumps(llm_schema, indent=2)}

Important guidelines:

- For 'persons', provide a comma-separated string of full names, converted to lowercase. If there is any fuzzy mistakes in name given by user, correct it to the best of your ability.
- For date-related fields:
- If the query refers to a *single specific day* (e.g., "photos from yesterday", "on June 23rd", "Christmas"), populate `date_query`
- If the query refers to a *single year* (e.g., "photos from 2023"), populate `date_query` with just the year.
- If the query specifies a *date range* (e.g., "from June 1st to June 15th", "between July and August"), populate `date_range_start` and `date_range_end`.
- If *only* time constraints are given without any specific date (e.g., "images before 4pm"), then only populate `start_time` and/or `end_time`, leave `date_query` and date range fields empty.
- Do NOT populate `date_query` if `date_range_start` or `date_range_end` are populated.
- Convert times like '9 AM' to '09:00' and '5 PM' to '17:00'. 'morning' typically means '06:00' to '12:00', 'evening' means '17:00' to '21:00'.
- For 'location_query', extract the *most specific* location name possible.

Strictly return only a JSON object. Do not include any additional text, markdown formatting (like ```json), or explanations.

Examples of user queries and expected JSON outputs:

- User: "photos from yesterday" -> JSON: {{"date_query": "yesterday"}}
- User: "images from June 23 before 4PM" -> JSON: {{"date_query": "June 23", "end_time": "16:00"}}
- User: "pictures taken on Christmas morning" -> JSON: {{"date_query": "Christmas", "start_time": "06:00", "end_time": "12:00"}}
- User: "photos from August 2024 after 10 AM" -> JSON: {{"date_query": "August 2024", "start_time": "10:00"}}
- User: "photos from 1st June to 29th June" -> JSON: {{"date_range_start": "June 1st", "date_range_end": "June 29th"}}
- User: "images of rohit sharma and virat kohli in Mumbai" -> JSON: {{"persons": "rohit sharma, virat kohli", "location_query": "Mumbai"}}
- User: "my pics from iPhone in 2023" -> JSON: {{"deviceType": "iPhone", "date_query": "2023"}}
- User: "photos from vacation folder taken last week" -> JSON: {{"localFolderName": "vacation folder", "date_query": "last week"}}
- User: "pictures of dogs at the park from Google Photos" -> JSON: {{"title": "dogs", "location_query": "park", "appName": "Google Photos"}}
- User: "show me images from march 2022 to july 2022" -> JSON: {{"date_range_start": "March 2022", "date_range_end": "July 2022"}}
- User: "find photos from 2020" -> JSON: {{"date_query": "2020"}}
- User: "photos from June 23 between 2pm to 3pm" -> JSON: {{"date_query": "June 23", "start_time": "14:00", "end_time": "15:00"}}
- User: "images before 4pm" -> JSON: {{"end_time": "16:00"}}
- User: "images taken after 5pm" -> JSON: {{"start_time": "17:00"}}
- User: "images between 2am to 12pm" -> JSON: {{"start_time": "02:00", "end_time": "12:00"}}
- User: "photos from 2021" -> JSON: {{"date_query": "2021"}}
- User: "images between March 2024 and July 2025 from 4pm to 6pm" -> JSON: {{"date_range_start": "March 2024", "date_range_end": "July 2025", "start_time": "16:00", "end_time": "18:00"}}

User Query: "{query}"

JSON Output:
"""

    try:
        response = client_openai.chat.completions.create(
            model=DEPLOYMENT,
            messages=[
                {"role": "system", "content": "You are a precise metadata extractor for photo queries. Only output JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=250,
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content.strip()
        print(f"--- Raw LLM Response Content ---\n{content}\n--------------------------------")

        if content.startswith("```"):
            content = re.sub(r"^```json\n?", "", content)
            content = re.sub(r"\n```$", "", content)

        raw_metadata = json.loads(content)
        final_metadata = {}

        for key in ["title", "persons", "image_path", "url", "basename", "appName", "deviceType", "localFolderName", "start_time", "end_time"]:
            if raw_metadata.get(key) is not None:
                final_metadata[key] = raw_metadata[key]

        if raw_metadata.get("persons"):
            cleaned_persons = []
            for person_phrase in raw_metadata["persons"].split(","):
                cleaned_name = person_phrase.strip().lower()
                cleaned_name = cleaned_name.replace("name ", "").strip()
                if cleaned_name:
                    cleaned_persons.append(cleaned_name)
            if cleaned_persons:
                final_metadata["persons"] = ", ".join(cleaned_persons)

        # --- Date Processing Logic ---
        start_date_str = raw_metadata.get("date_range_start")
        end_date_str = raw_metadata.get("date_range_end")
        single_date_str = raw_metadata.get("date_query")

        now_utc = datetime.datetime.now(datetime.timezone.utc)

        year_pattern = re.compile(r"^\s*\d{4}\s*$")
        month_year_pattern = re.compile(r"^(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}$", re.IGNORECASE)

        if start_date_str and end_date_str:
            try:
                parsed_start_date_obj = parse(
                    start_date_str,
                    settings={
                        'RELATIVE_BASE': now_utc,
                        'RETURN_AS_TIMEZONE_AWARE': True,
                        'TIMEZONE': 'UTC',
                        'TO_TIMEZONE': 'UTC',
                        'PREFER_DATES_FROM': 'past',
                        'STRICT_PARSING': False
                    }
                )
                parsed_end_date_obj = parse(
                    end_date_str,
                    settings={
                        'RELATIVE_BASE': now_utc,
                        'RETURN_AS_TIMEZONE_AWARE': True,
                        'TIMEZONE': 'UTC',
                        'TO_TIMEZONE': 'UTC',
                        'PREFER_DATES_FROM': 'past',
                        'STRICT_PARSING': False
                    }
                )

                if parsed_start_date_obj and parsed_end_date_obj:
                    if year_pattern.match(start_date_str):
                        final_metadata["start_date_parsed_object"] = parsed_start_date_obj.replace(
                            month=1, day=1, hour=0, minute=0, second=0, microsecond=0
                        )
                    elif month_year_pattern.match(start_date_str):
                        final_metadata["start_date_parsed_object"] = parsed_start_date_obj.replace(
                            day=1, hour=0, minute=0, second=0, microsecond=0
                        )
                    else:
                        final_metadata["start_date_parsed_object"] = parsed_start_date_obj.replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )

                    if year_pattern.match(end_date_str):
                        final_metadata["end_date_parsed_object"] = parsed_end_date_obj.replace(
                            month=12, day=31, hour=23, minute=59, second=59, microsecond=999999
                        )
                    elif month_year_pattern.match(end_date_str):
                        next_month = parsed_end_date_obj.replace(day=1) + datetime.timedelta(days=32)
                        last_day_of_month = next_month.replace(day=1) - datetime.timedelta(days=1)
                        final_metadata["end_date_parsed_object"] = last_day_of_month.replace(
                            hour=23, minute=59, second=59, microsecond=999999
                        )
                    else:
                        final_metadata["end_date_parsed_object"] = parsed_end_date_obj.replace(
                            hour=23, minute=59, second=59, microsecond=999999
                        )
                else:
                    print(f"⚠️ dateparser could not parse one or both date range parts: '{start_date_str}' or '{end_date_str}'")
            except Exception as e:
                print(f"⚠️ Error parsing date range '{start_date_str}' to '{end_date_str}': {e}")

        elif single_date_str:
            try:
                if year_pattern.match(single_date_str):
                    year = int(single_date_str)
                    final_metadata["start_date_parsed_object"] = datetime.datetime(year, 1, 1, 0, 0, 0, 0, tzinfo=datetime.timezone.utc)
                    final_metadata["end_date_parsed_object"] = datetime.datetime(year, 12, 31, 23, 59, 59, 999999, tzinfo=datetime.timezone.utc)
                else:
                    parsed_single_date_obj = parse(
                        single_date_str,
                        settings={
                            'RELATIVE_BASE': now_utc,
                            'RETURN_AS_TIMEZONE_AWARE': True,
                            'TIMEZONE': 'UTC',
                            'TO_TIMEZONE': 'UTC',
                            'PREFER_DATES_FROM': 'past',
                            'STRICT_PARSING': False
                        }
                    )
                    if parsed_single_date_obj:
                        final_metadata["start_date_parsed_object"] = parsed_single_date_obj.replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )
                        final_metadata["end_date_parsed_object"] = parsed_single_date_obj.replace(
                            hour=23, minute=59, second=59, microsecond=999999
                        )
                    else:
                        print(f"⚠️ dateparser could not parse single date: '{single_date_str}'")
            except Exception as e:
                print(f"⚠️ Error parsing single date '{single_date_str}': {e}")

        if raw_metadata.get("location_query"):
            location_name = raw_metadata["location_query"]
            try:
                location = geolocator.geocode(location_name)
                if location:
                    final_metadata["latitude"] = location.latitude
                    final_metadata["longitude"] = location.longitude
                    final_metadata["radius_km"] = raw_metadata.get("radius_km", 5000)
                else:
                    print(f"⚠️ Could not geocode location: '{location_name}' (No results found)")
            except (GeocoderTimedOut, GeocoderServiceError) as e:
                print(f"⚠️ Geocoding service error for '{location_name}': {e}")
            except Exception as e:
                print(f"⚠️ Unexpected error during geocoding for '{location_name}': {e}")

        return final_metadata

    except json.JSONDecodeError as e:
        print(f"❌ Error decoding JSON from OpenAI response: {e}")
        print(f"Raw content from OpenAI: {content}")
        return {}
    except Exception as e:
        print(f"❌ An unexpected error occurred in metadata_extractor: {e}")
        return {}
