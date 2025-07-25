import json
import re
import random
from typing import List, Dict, Set, Tuple
from openai import AzureOpenAI
import sys
from dotenv import load_dotenv
import os

# ✅ Load .env file from current directory
load_dotenv()

class ResumeRetailorNoJD:
    def __init__(self, azure_config: Dict[str, str]):
        """
        Initialize the resume retailor with Azure OpenAI configuration.
        
        Args:
            azure_config: Dictionary containing Azure OpenAI configuration
                - api_key: Azure OpenAI API key
                - api_version: API version
                - endpoint: Azure endpoint
                - deployment: Model deployment name
        """
        api_key = os.environ.get('OPENAI_API_KEY')
        api_version = "2024-08-01-preview"
        azure_endpoint = "https://us-tax-law-rag-demo.openai.azure.com/"
        deployment_name = "gpt-4o-mini"

        self.client = AzureOpenAI(
            api_key=api_key,
            api_version=api_version,
            azure_endpoint=azure_endpoint
        )
        self.deployment_name = deployment_name
    
    def convert_objectid_to_str(self, obj):
        """Convert ObjectId to string for JSON serialization."""
        if isinstance(obj, dict):
            return {k: self.convert_objectid_to_str(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.convert_objectid_to_str(i) for i in obj]
        elif hasattr(obj, '__class__') and obj.__class__.__name__ == "ObjectId":
            return str(obj)
        else:
            return obj
    
    def extract_all_projects(self, resume: Dict) -> list:
        """Extract ALL projects from both 'projects' and 'experience' sections."""
        all_projects = []
        
        # Process original projects
        for proj in resume.get('projects', []):
            all_projects.append(proj)
        
        # Process experience descriptions and extract as projects
        for exp in resume.get('experience', []):
            # Create a project-like dict from experience
            exp_project = {
                'title': exp.get('title', exp.get('position', 'Professional Experience')),
                'description': exp.get('description', ''),
                'technologies': exp.get('technologies', []) if 'technologies' in exp else [],
                'company': exp.get('company', ''),
                'duration': exp.get('duration', ''),
                'source': 'experience'  # Mark source for reference
            }
            all_projects.append(exp_project)
        
        return all_projects

    
    @staticmethod
    def _normalize_title(text):
        """Normalize text for strict comparison: lowercase, remove whitespace and punctuation."""
        import string
        return ''.join(c for c in text.lower() if c not in string.whitespace + string.punctuation)
    
    def universal_enhance_project_title(self, project: Dict) -> str:

        original_title = project.get('title', '').strip()
        description = project.get('description', '')
        technologies = project.get('technologies', [])

        # If the original title is missing, create a placeholder to guide the LLM
        if not original_title:
            original_title = "Untitled Technical Project"

        # This enhanced prompt gives the LLM clearer instructions and context,
        # empowering it to create a superior title based on the project's substance.
        prompt = f"""You are an expert resume writer. Your task is to rewrite a project title to be specific, impactful, and highlight the core technical achievement.

    **Project Context:**
    - **Original Title:** "{original_title}"
    - **Description:** "{description}"
    - **Technologies Used:** "{', '.join(technologies) if technologies else 'Not specified'}"

    **CRITICAL INSTRUCTIONS:**
    1.  **Create a NEW Title:** Your primary goal is to generate a title that is fundamentally different and more descriptive than the original. DO NOT simply rephrase the original title.
    2.  **Focus on the Achievement:** Analyze the description to understand what was built, solved, or created. The title should reflect this outcome (e.g., "Automated Data Pipeline," "Scalable E-commerce Platform," "Real-time Chat Application").
    3.  **Lead with Technology (If Applicable):** If a key technology is central to the project, use it to frame the title (e.g., "Python-Based API," "React-Powered Dashboard").
    4.  **Be Specific and Professional:** Avoid generic titles. Make it sound like a real-world project.
    5.  **Return ONLY the new title:** Your response must be a single line containing the title and nothing else.

    **Examples of Strong Transformations:**
    - Original: "My E-commerce Site" -> New: "Full-Stack E-commerce Platform with Stripe Integration"
    - Original: "Data Project" -> New: "Python-Driven ETL Pipeline for Sales Data Analytics"
    - Original: "Resume tool" -> New: "n8n-Powered Workflow for Automated Resume Tailoring"

    Rewrite the title based on the context provided:"""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are a highly skilled resume and technical writer."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,  # Slightly increased for more creative and diverse titles
                response_format={"type": "text"}
            )
            enhanced_title = response.choices[0].message.content.strip().strip('"\'')

            # Safety Check: If the LLM fails to produce a new or valid title,
            # programmatically create a different one without calling the old helper function.
            is_same_title = self._normalize_title(enhanced_title) == self._normalize_title(original_title)
            if not enhanced_title or is_same_title:
                # Create a simple, guaranteed-different title as a fallback
                return f"Optimized: {original_title}"

            return enhanced_title

        except Exception as e:
            print(f"Error enhancing project title with LLM: {str(e)}", file=sys.stderr)
            # Robust, non-LLM fallback in case of API failure.
            # This ensures the script never crashes and always returns a valid, different title.
            return f"Professional Project: {original_title}"
    
    def generate_professional_summary(self, candidate: Dict) -> str:
        """
        Generates or enhances a professional summary based on a candidate's profile.
        
        This function pre-processes the candidate's data into a clean summary to help the LLM
        craft a compelling, narrative-driven summary that highlights their key value.
        """
        existing_summary = candidate.get('summary', '').strip()

        # --- Data Summarization Step ---
        # Convert raw data into easy-to-read highlights for the LLM.
        
        # Summarize experience by listing job titles
        experience_titles = [exp.get('title') for exp in candidate.get('experience', []) if exp.get('title')]
        experience_summary = f"Career path includes roles like: {', '.join(experience_titles)}." if experience_titles else ""

        # Summarize projects by listing their titles
        project_titles = [p.get('title') for p in candidate.get('projects', []) if p.get('title')]
        project_summary = f"Developed key projects such as: '{', '.join(project_titles)}'." if project_titles else ""

        # List top skills
        skills_summary = ', '.join([str(s) for s in candidate.get('skills', [])[:15] if s])

        # --- Enhanced Prompt ---
        # This prompt provides a clear structure and narrative guidance.
        prompt = f"""You are an expert resume writer, crafting a compelling professional summary for a candidate. The goal is to create a concise (3-4 sentences) and powerful pitch based on their profile.

    **Candidate Highlights:**
    - **Professional Title:** {candidate.get('title', 'N/A')}
    - **Key Skills:** {skills_summary}
    - **Experience Snapshot:** {experience_summary}
    - **Project Snapshot:** {project_summary}
    - **Existing Summary (for reference):** "{existing_summary if existing_summary else 'None'}"

    **Instructions:**
    1.  **Adopt a Professional Tone:** Write a confident summary as if you are highlighting the candidate's top qualifications. Use an implied first-person or formal third-person voice (e.g., "A results-driven professional..." or "Highly skilled in...").
    2.  **Create a Narrative:**
        - Start with a strong opening statement defining the candidate (e.g., "A highly motivated Software Engineer...").
        - Weave in 2-3 key skills or technologies from their profile that are most impressive.
        - Mention a key achievement or area of expertise demonstrated in their experience or projects.
        - Conclude with their core value proposition.
    3.  **Be Fact-Based:** Do not invent or exaggerate information. Ground every statement in the provided profile highlights.
    4.  **Format:** The final output must be a single paragraph of 3-4 sentences. Do NOT include any headers, labels, or quotation marks.

    **Rewrite or generate the professional summary:**"""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are a top-tier resume writer and career strategist."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,  # A higher temperature for more natural, compelling language
                response_format={"type": "text"}
            )
            
            summary = response.choices[0].message.content.strip()
            # Fallback to the original if the model returns something too short or empty
            return summary if len(summary) > 20 else existing_summary

        except Exception as e:
            print(f"Error generating summary: {str(e)}", file=sys.stderr)
            # Fallback to the original summary in case of any API error
            return existing_summary or candidate.get('summary', '')
    
    def generate_tailored_title(self, candidate: Dict, job_keywords: Set[str] = None) -> str:
        """
        Generates a professional job title based on the candidate's profile.
        If job_keywords are provided, it tailors the title to align with the job description.
        """
        # 1. Pre-process and summarize the candidate's data for a cleaner prompt
        experience_summary = [f"- {exp.get('title', '')} at {exp.get('company', '')}" for exp in candidate.get('experience', [])]
        skills_summary = ', '.join([str(s) for s in candidate.get('skills', [])[:10] if s]) # Top 10 skills

        # Base prompt with clear context
        prompt_lines = [
            "Based on the following professional profile, generate a single, industry-standard job title.",
            "\n**Candidate Profile:**",
            f"- **Current/Recent Title:** {candidate.get('title', 'N/A')}",
            f"- **Key Skills:** {skills_summary}",
            "- **Experience History:**",
            *experience_summary, # Unpack the list of experience strings
        ]

        # 2. Dynamically add context if job keywords are available
        if job_keywords:
            prompt_lines.extend([
                "\n**Target Job Keywords:**",
                f"{', '.join(job_keywords)}",
                "\n**Instructions:**",
                "1. Analyze the candidate's skills and experience level.",
                "2. Propose a title that aligns with BOTH the candidate's profile AND the job keywords.",
                "3. Ensure the title accurately reflects their seniority (do not overstate).",
                "4. Return ONLY the job title, nothing else."
            ])
        else:
            prompt_lines.extend([
                "\n**Instructions:**",
                "1. Analyze the candidate's overall skills and experience.",
                "2. Propose a title that best summarizes their professional standing.",
                "3. Ensure the title accurately reflects their seniority.",
                "4. Return ONLY the job title, nothing else."
            ])
        
        final_prompt = "\n".join(prompt_lines)

        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are a senior technical recruiter and career coach who excels at crafting accurate job titles."},
                    {"role": "user", "content": final_prompt}
                ],
                temperature=0.2, # Lower temperature for more deterministic, accurate titles
                response_format={"type": "text"}
            )
            
            title = response.choices[0].message.content.strip().strip('"')
            
            # Final safety check to ensure a valid title is returned
            return title if title else candidate.get('title', '')
            
        except Exception as e:
            print(f"Error generating job title: {str(e)}", file=sys.stderr)
            # Fallback to the original title if there's an API error
            return candidate.get('title', '')
    
    def retailor_resume_no_jd(self, original_resume: Dict) -> Dict:
        """
        Retailor the resume without a job description:
        - Enhances all project titles (including work experience converted to projects)
        - Keeps descriptions unchanged
        - Generates professional summary and title
        - Maintains original skills
        """
        # Convert ObjectId to string for JSON serialization
        safe_resume = self.convert_objectid_to_str(original_resume)
        job_keywords = set(safe_resume.get('keywords', []))
        
        # Extract ALL projects from both projects and experience sections
        all_projects = self.extract_all_projects(safe_resume)
        
        # Enhance titles for all projects (including work experience)
        enhanced_projects = []
        for proj in all_projects:
            enhanced_title = self.universal_enhance_project_title(proj)
            proj_copy = proj.copy()
            proj_copy['title'] = enhanced_title
            # Description remains unchanged when no JD  
            enhanced_projects.append(proj_copy)
        
        # Update the resume with enhanced project titles
        safe_resume['projects'] = enhanced_projects
        
        # Generate professional title if not present
        if not safe_resume.get("title"):
            safe_resume["title"] = self.generate_tailored_title(safe_resume,job_keywords)
        
        # Generate professional summary if not present
        if not safe_resume.get("summary"):
            safe_resume["summary"] = self.generate_professional_summary(safe_resume)
        
        return safe_resume

def main():
    """
    Reads resume from stdin, retailors it, and prints to stdout.
    """
    try:
        # Example Azure OpenAI configuration (replace with your actual credentials)
        azure_config = {
            "api_key": os.environ.get('OPENAI_API_KEY'),
            "api_version": "2024-02-01",
            "endpoint": "https://resumeparser-dev.openai.azure.com/",
            "deployment": "gpt4o-mini"
        }
        
        # Read resume data from stdin
        input_resume = json.load(sys.stdin)
        
        # Initialize the retailor
        retailor = ResumeRetailorNoJD(azure_config)
        
        # Retailor the resume
        retailored_resume = retailor.retailor_resume_no_jd(input_resume)
        
        # Print the retailored resume to stdout
        print(json.dumps(retailored_resume, indent=2))
        
    except json.JSONDecodeError:
        print(json.dumps({"error": "Invalid JSON input"}), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": f"An unexpected error occurred: {str(e)}"}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
