import os
import json
import asyncio
import argparse
import sys
import uuid
import datetime
import logging
import boto3
import zipfile
import tempfile
from pathlib import Path
from typing import Dict
from openai import AsyncOpenAI
from dotenv import load_dotenv
import httpx
from aiohttp import ClientSession

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()
# S3 config
S3_BUCKET = os.getenv("AWS_S3_BUCKET_NAME")
S3_PREFIX = os.getenv("AWS_S3_PREFIX", "qti_packages/")  # Default to empty string if not set

def questions_to_qti_xml(questions: list, session_id: str) -> str:
    items = []
    for idx, q in enumerate(questions):
        qid = f"{session_id}_q{idx+1}"
        if q["type"] == "MCQ":
            choices = "".join(
                f'<simpleChoice identifier="A{i+1}">{c}</simpleChoice>' for i, c in enumerate(q["options"])
            )
            correct = q["options"].index(q["correct_answer"]) if q["correct_answer"] in q["options"] else 0
            item = f"""
<assessmentItem identifier="{qid}" title="{q['question']}" timeDependent="false">
  <responseDeclaration identifier="RESPONSE" cardinality="single" baseType="identifier">
    <correctResponse>
      <value>A{correct+1}</value>
    </correctResponse>
  </responseDeclaration>
  <itemBody>
    <choiceInteraction responseIdentifier="RESPONSE" shuffle="false" maxChoices="1">
      <prompt>{q['question']}</prompt>
      {choices}
    </choiceInteraction>
  </itemBody>
</assessmentItem>
"""
        elif q["type"] == "T/F":
            correct = "true" if str(q["correct_answer"]).lower() == "true" else "false"
            item = f"""
<assessmentItem identifier="{qid}" title="{q['question']}" timeDependent="false">
  <responseDeclaration identifier="RESPONSE" cardinality="single" baseType="boolean">
    <correctResponse>
      <value>{correct}</value>
    </correctResponse>
  </responseDeclaration>
  <itemBody>
    <choiceInteraction responseIdentifier="RESPONSE" shuffle="false" maxChoices="1">
      <prompt>{q['question']}</prompt>
      <simpleChoice identifier="A1">True</simpleChoice>
      <simpleChoice identifier="A2">False</simpleChoice>
    </choiceInteraction>
  </itemBody>
</assessmentItem>
"""
        elif q["type"] == "Short-answer":
            item = f"""
<assessmentItem identifier="{qid}" title="{q['question']}" timeDependent="false">
  <responseDeclaration identifier="RESPONSE" cardinality="single" baseType="string">
    <correctResponse>
      <value>{q['correct_answer']}</value>
    </correctResponse>
  </responseDeclaration>
  <itemBody>
    <extendedTextInteraction responseIdentifier="RESPONSE" expectedLength="50">
      <prompt>{q['question']}</prompt>
    </extendedTextInteraction>
  </itemBody>
</assessmentItem>
"""
        else:
            continue
        items.append(item)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<assessmentTest xmlns="http://www.imsglobal.org/xsd/imsqti_v2p1">
  {''.join(items)}
</assessmentTest>
"""

def create_qti_zip(questions: list, session_id: str, questions_json: dict) -> str:
    try:
        logger.info("Generating QTI XML")
        qti_xml = questions_to_qti_xml(questions, session_id)
        if not isinstance(qti_xml, str):
            logger.error(f"QTI XML is not a string, got type: {type(qti_xml)}")
            raise TypeError(f"Expected string for QTI XML, got {type(qti_xml)}")
            
        logger.info("Creating temporary directory")
        with tempfile.TemporaryDirectory() as tmpdir:
            xml_path = Path(tmpdir) / "assessment.xml"
            logger.info(f"Writing XML to: {xml_path}")
            with open(xml_path, "w", encoding="utf-8") as f:
                f.write(qti_xml)
                
            json_path = Path(tmpdir) / "questions.json"
            logger.info(f"Writing JSON to: {json_path}")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(questions_json, f, indent=2, ensure_ascii=False)
                
            zip_path = Path(tmpdir) / f"{session_id}_qti.zip"
            logger.info(f"Creating zip file at: {zip_path}")
            with zipfile.ZipFile(zip_path, "w") as zipf:
                zipf.write(xml_path, arcname="assessment.xml")
                zipf.write(json_path, arcname="questions.json")
                
            final_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            logger.info(f"Copying zip to permanent location: {final_zip.name}")
            with open(zip_path, "rb") as src, open(final_zip.name, "wb") as dst:
                dst.write(src.read())
            return final_zip.name
    except Exception as e:
        logger.error(f"Error in create_qti_zip: {str(e)}")
        logger.error(f"Questions type: {type(questions)}")
        logger.error(f"Session ID type: {type(session_id)}")
        logger.error(f"Questions JSON type: {type(questions_json)}")
        if isinstance(questions, list):
            logger.error(f"Number of questions: {len(questions)}")
            if questions:
                logger.error(f"First question type: {type(questions[0])}")
                logger.error(f"First question content: {questions[0]}")
        raise

def upload_to_s3(zip_path: str, s3_key: str) -> str:
    if not S3_BUCKET:
        raise ValueError("AWS_S3_BUCKET_NAME environment variable is not set")
        
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    
    if not aws_access_key or not aws_secret_key:
        raise ValueError("AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables must be set")
    
    s3 = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key
    )
    
    logger.info(f"Uploading file {zip_path} to S3 bucket {S3_BUCKET} with key {s3_key}")
    s3.upload_file(zip_path, S3_BUCKET, s3_key)
    return f"https://{S3_BUCKET}.s3.amazonaws.com/{s3_key}"

class QuestionGenerator:
    def __init__(self):
        load_dotenv()
        self.openai_client = None
        self.httpx_client = None
        self.session = None

    async def initialize_clients(self):
        if not self.openai_client:
            self.session = ClientSession()
            self.httpx_client = httpx.AsyncClient()
            self.openai_client = AsyncOpenAI(
                api_key=os.getenv("OPENAI_API_KEY"),
                http_client=self.httpx_client
            )

    async def cleanup(self):
        if self.session and not self.session.closed:
            await self.session.close()
        if self.httpx_client and not self.httpx_client.is_closed:
            await self.httpx_client.aclose()

    async def generate_questions(self, text: str, session_id: str) -> Dict:
        await self.initialize_clients()

        prompt = f"""Generate a JSON object for a quiz based on the following text.
        The JSON object should have a "questions" array containing exactly 15 questions in total, with:
        - 5 multiple choice questions (type: "MCQ")
        - 5 true/false questions (type: "T/F")
        - 5 short answer questions (type: "Short-answer")

        Each question in the "questions" array MUST strictly follow this schema:
        {{
            "session_id": "{session_id}",
            "type": "MCQ" | "T/F" | "Short-answer",
            "question": "<question text>",
            "options": [<array of options>],  // Only for MCQ, omit for others
            "correct_answer": "<correct answer>",
            "difficulty": "easy" | "medium" | "hard",
            "tags": [<array of tags>]
        }}

        - For MCQ, include the "options" field as an array of 4 choices.
        - For T/F and Short-answer, omit the "options" field.
        - All fields are required except "options" (which is only for MCQ).
        - Use the provided session_id for all questions.
        - Ensure the questions are relevant to the provided text and well distributed across difficulty levels and tags.

        JSON Structure:
        {{
            "questions": [
                {{
                    "session_id": "{session_id}",
                    "type": "MCQ",
                    "question": "What does R² measure in regression?",
                    "options": ["Fit", "Bias", "Mean", "Variance"],
                    "correct_answer": "Fit",
                    "difficulty": "medium",
                    "tags": ["regression", "statistics"]
                }},
                ...
            ]
        }}

        Text to generate questions from:
        {text}

        Return only the JSON object, no extra text.
        """

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": "You are an expert educator creating high-quality assessment questions that strictly adhere to the specified JSON format. Each question MUST include all required fields."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=4000,
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content
            if not isinstance(content, str):
                logger.error(f"Unexpected content type from API: {type(content)}")
                raise TypeError("API response content must be a string")
                
            try:
                questions_payload = json.loads(content)
                logger.info("Successfully parsed JSON from API response")
            except json.JSONDecodeError as e:
                logger.error(f"JSON decoding error: {e}. Raw content (first 500 chars): {content[:500]}...")
                logger.error(f"Raw content (last 500 chars): ...{content[-500:]}")
                raise
            
            # Validate questions structure
            if "questions" not in questions_payload:
                raise ValueError("Missing 'questions' field in API response")
            
            logger.info(f"Found {len(questions_payload['questions'])} questions in payload")
            
            for idx, question in enumerate(questions_payload["questions"]):
                required_fields = ["session_id", "type", "question", "correct_answer"]
                missing_fields = [field for field in required_fields if field not in question]
                if missing_fields:
                    raise ValueError(f"Question {idx + 1} is missing required fields: {', '.join(missing_fields)}")
                
                if question["type"] == "MCQ" and "options" not in question:
                    raise ValueError(f"MCQ question {idx + 1} is missing 'options' field")
            
            questions_payload["_id"] = str(uuid.uuid4())
            questions_payload["unit_outline_id"] = str(uuid.uuid4())
            questions_payload["session_ids"] = [session_id]
            
            # QTI zip creation and S3 upload (include JSON in zip)
            questions = questions_payload["questions"]
            logger.info("Starting QTI zip creation")
            zip_path = create_qti_zip(questions, session_id, questions_payload)
            logger.info(f"Created QTI zip at: {zip_path}")
            
            s3_key = f"{S3_PREFIX}{session_id}_qti.zip"
            logger.info(f"Uploading to S3 with key: {s3_key}")
            qti_url = upload_to_s3(zip_path, s3_key)
            logger.info(f"Successfully uploaded to S3: {qti_url}")
            
            questions_payload["qti_zip_url"] = qti_url

            questions_payload["generated_by"] = str(uuid.uuid4())
            questions_payload["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
            questions_payload["version"] = 1
            questions_payload["is_latest"] = True

            return questions_payload

        except Exception as e:
            logger.error(f"Error generating questions: {str(e)}")
            raise

async def main():
    generator = QuestionGenerator()

    parser = argparse.ArgumentParser(description='Generate questions from text content.')
    parser.add_argument('--session-id', type=str, required=True, help='Session ID (e.g., S3 object key or a unique identifier).')
    args = parser.parse_args()

    text_content = sys.stdin.read()
    if not text_content:
        logger.error("No content received from stdin.")
        print("Error: No content received from stdin.", file=sys.stderr)
        sys.exit(1)

    try:
        logger.info(f"Generating questions for session: {args.session_id}")
        questions_json = await generator.generate_questions(text_content, args.session_id)
        
        # Print JSON to stdout for NiFi InvokeHTTP processor
        print(json.dumps(questions_json, indent=2, ensure_ascii=False))
        logger.info(f"Successfully generated and outputted questions for session: {args.session_id}")
        sys.exit(0)

    except Exception as e:
        logger.error(f"Error in main process: {str(e)}")
        print(f"Error processing content: {str(e)}", file=sys.stderr)
        sys.exit(1)
    finally:
        await generator.cleanup()

if __name__ == "__main__":
    asyncio.run(main()) 