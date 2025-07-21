#!/usr/bin/env python3
import sys
import json
import os
from openai import AzureOpenAI

class CandidateScorer:
    def __init__(self):
        api_key = ""
        api_version = "2024-08-01-preview"
        azure_endpoint = "https://us-tax-law-rag-demo.openai.azure.com/"
        deployment_name = "gpt-4o-mini"

        if not all([api_key, api_version, azure_endpoint, deployment_name]):
            raise ValueError("Missing Azure OpenAI environment variables.")

        self.client = AzureOpenAI(
            api_key=api_key,
            api_version=api_version,
            azure_endpoint=azure_endpoint
        )
        self.deployment_name = deployment_name

    def calculate_score(self, resume: dict) -> dict:
        keywords = resume.get("keywords", [])
        name = resume.get("name", "Unknown")
        skills = resume.get("skills", [])
        projects = resume.get("projects", [])

        if not keywords:
            return {
                "score": 0,
                "reason": "No job description keywords provided.",
                "status": "Rejected"
            }

        prompt = f"""You are an AI designed to evaluate candidate suitability for a job based on pre-extracted job description keywords. Compare the candidate's skills and projects against the job description keywords and assign a holistic match score.

### Job Description Keywords:
{json.dumps(keywords)}

### Candidate Details:
- Name: {name}
- Skills: {json.dumps(skills)}
- Projects: {json.dumps(projects)}

Scoring Rules:
- Score 1–100
- Status: "Accepted" if score > 70, else "Rejected"
- Keep reason under 50 words

Output **valid JSON** exactly in this shape:
{{
  "score": <1–100>,
  "reason": "<detailed explanation mentioning hits/misses>",
  "status": "<Accepted or Rejected>"
}}"""

        try:
            resp = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )

            text = resp.choices[0].message.content.strip()
            if text.startswith("```json"):
                text = text.replace("```json", "").replace("```", "").strip()

            result = json.loads(text)

            for field in ("score", "reason", "status"):
                if field not in result:
                    raise ValueError(f"LLM response missing '{field}'")

            result["score"] = int(float(result.get("score", 0)))
            if result["status"] not in ("Accepted", "Rejected"):
                result["status"] = "Accepted" if result["score"] > 70 else "Rejected"

            return result

        except Exception as e:
            return {
                "score": 0,
                "reason": f"Error during evaluation: {e}",
                "status": "Rejected"
            }

def main():
    try:
        raw = sys.stdin.read()
        resumes = json.loads(raw)

        if not isinstance(resumes, list):
            raise ValueError("Expected input to be a list of resumes.")

        scorer = CandidateScorer()
        scored_results = []

        for resume in resumes:
            scored = scorer.calculate_score(resume)
            scored_results.append({
                "name": resume.get("name", ""),
                "email": resume.get("email", ""),
                "phone": resume.get("phone", ""),
                "employee_id": resume.get("employee_id", ""),
                "score": scored.get("score", 0),
                "reason": scored.get("reason", ""),
                "keywords": resume.get("keywords", []),
                "job_description": resume.get("job_description", "")
            })

        print(json.dumps(scored_results, indent=2))

    except json.JSONDecodeError as e:
        err = {"error": f"Invalid input JSON: {e}"}
        print(json.dumps(err), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        err = {"error": f"Unexpected error: {e}"}
        print(json.dumps(err), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

