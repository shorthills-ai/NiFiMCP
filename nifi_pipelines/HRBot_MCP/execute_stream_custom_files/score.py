#!/usr/bin/env python3
import sys
import json
import os
from openai import AzureOpenAI
from typing import Dict, Set
from datetime import datetime

class CandidateScorer:
    def __init__(self):
        api_key = os.getenv("AZURE_API_KEY")
        api_version = os.getenv("AZURE_API_VERSION")
        endpoint = os.getenv("AZURE_ENDPOINT")
        deployment = os.getenv("AZURE_DEPLOYMENT")

        if not api_key or not endpoint:
            raise ValueError("Missing required Azure credentials environment variables. Check NiFi processor configuration.")

        self.client = AzureOpenAI(
            api_key=api_key,
            api_version=api_version,
            azure_endpoint=endpoint
        )
        self.deployment_name = deployment
        self.input_cost_per_1k = 0.000165
        self.output_cost_per_1k = 0.000660

    def log_llm_usage(self, response, prompt_type):
        """Log LLM usage statistics to stderr with timestamp."""
        try:
            timestamp = datetime.now().isoformat()
            usage = getattr(response, 'usage', None)
            if usage:
                prompt_tokens = usage.prompt_tokens
                completion_tokens = usage.completion_tokens
                input_cost = (prompt_tokens / 1000) * self.input_cost_per_1k
                output_cost = (completion_tokens / 1000) * self.output_cost_per_1k
                total_cost = input_cost + output_cost
                print(
                    f"LLM_USAGE | timestamp={timestamp} | model={self.deployment_name} | type={prompt_type} | prompt_tokens={prompt_tokens} | completion_tokens={completion_tokens} | total_cost=${total_cost:.6f}",
                    file=sys.stderr
                )
                
        except Exception as e:
            print(f"LLM_USAGE_LOG_ERROR: {e}", file=sys.stderr)

    def calculate_score(self, resume: dict) -> dict:
        """
        Main entry point. Validates input and calls the LLM evaluator.
        """
        keywords = resume.get("keywords", [])
        if not keywords:
            return {
                "score": 0,
                "reason": {
                    "summary": "No job description keywords provided in the input.",
                    "strengths": "N/A",
                    "gaps": "Cannot perform evaluation without keywords."
                },
                "status": "Rejected"
            }
        return self.evaluate_candidate(resume, set(keywords))

    def evaluate_candidate(self, candidate: Dict, keywords: Set[str]) -> Dict:
        """
        Builds the prompt and calls the LLM to get the score.
        """
        skills_summary = ", ".join(candidate.get('skills', []))
        experience_summary = "\n".join([f"- {exp.get('title', 'N/A')} at {exp.get('company', 'N/A')}" for exp in candidate.get('experience', [])])
        project_summary = "\n".join([f"- {proj.get('title', 'N/A')}: {proj.get('description', '')[:150]}..." for proj in candidate.get('projects', [])])

        prompt = f"""
    You are a senior technical recruiter and hiring strategist. Evaluate the candidate's profile against the job keywords.

    **### Candidate Profile ###**
    *   **Professional Title:** {candidate.get('title', 'N/A')}
    *   **Skills:** {skills_summary}
    *   **Experience History:**
{experience_summary}
    *   **Key Projects:**
{project_summary}

    **### Job Keywords ###**
    {json.dumps(list(keywords))}

    **### Scoring Rubric & Logic ###**
    *   90-100 (Exceptional): Direct experience with nearly all keywords.
    *   75-89 (Strong): Experience with most important keywords. Hireable.
    *   60-74 (Potential): Partial match with transferable skills.
    *   Below 60 (Not a Fit): Significant gaps.

    **### Output Format ###**
    You MUST return a valid JSON object.
    {{
    "score": <integer>,
    "reason": {{
        "summary": "<1-2 sentence executive summary.>",
        "strengths": "<Bulleted list of matching skills.>",
        "gaps": "<Bulleted list of missing requirements.>"
    }},
    "status": "<'Accepted' for scores 75+, 'Rejected' otherwise>"
    }}
    """
        try:
            resp = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            self.log_llm_usage(resp, "score_evaluation")
            result = json.loads(resp.choices[0].message.content)

            # Validate LLM response structure
            if not all(k in result for k in ("score", "reason", "status")):
                raise ValueError("LLM response missing required fields.")
            if not isinstance(result.get("reason"), dict) or not all(k in result["reason"] for k in ["summary", "strengths", "gaps"]):
                raise ValueError("LLM 'reason' field is not structured correctly.")

            result["score"] = int(float(result.get("score", 0)))
            if result["status"] not in ("Accepted", "Rejected"):
                result["status"] = "Accepted" if result["score"] >= 75 else "Rejected"
            return result
        except Exception as e:
            return {
                "score": 0,
                "reason": {
                    "summary": "Failed to evaluate candidate due to an error.",
                    "strengths": "N/A",
                    "gaps": f"Error: {e}"
                },
                "status": "Rejected"
            }

def main():
    original_stderr = sys.stderr
    log_file_path = "/home/nifi/nifi2/users/HR_Teams_Bot_Dev/llm_usage.log"
    try:
        with open(log_file_path, 'a') as log_file:
            sys.stderr = log_file
            raw = sys.stdin.read()
            resumes = json.loads(raw)
            if not isinstance(resumes, list):
                resumes = [resumes]

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
                    "reason": scored.get("reason", {}),
                    "status": scored.get("status", "Rejected"),
                    "keywords": resume.get("keywords", []),
                    "job_description": resume.get("job_description", "")
                })
            print(json.dumps(scored_results, indent=2))
    except Exception as e:
        print(json.dumps({"error": f"Unexpected error in main: {e}"}), file=sys.stderr)
        sys.exit(1)
    finally:
        sys.stderr = original_stderr

if __name__ == "__main__":
    main()