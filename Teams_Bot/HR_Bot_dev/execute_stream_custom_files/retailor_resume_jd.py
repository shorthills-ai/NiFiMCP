#!/usr/bin/env python3
"""
Resume Retailor with Job Description Keywords
This script retailors resumes using keywords that are present in the resume's keywords attribute.
It enhances both project titles and descriptions using the job description keywords.
"""
import sys
import json
from typing import List, Dict, Set, Tuple
from openai import AzureOpenAI
import difflib
import string
from dotenv import load_dotenv
import os

# ✅ Load .env file from current directory
load_dotenv()


class ResumeRetailorWithJD:
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
  
    def extract_all_projects(self, resume: Dict) -> list:
        """Extract ALL projects from both 'projects' and 'experience' sections."""
        all_projects = []
        
        # Process original projects
        for proj in resume.get('projects', []):
            proj_copy = proj.copy()
            proj_copy['source'] = 'projects'
            all_projects.append(proj_copy)
        
        # Process experience descriptions and extract as projects
        for exp in resume.get('experience', []):
            exp_project = {
                'title': exp.get('title', exp.get('position', 'Professional Experience')),
                'description': exp.get('description', ''),
                'technologies': exp.get('technologies', []) if 'technologies' in exp else [],
                'company': exp.get('company', ''),
                'duration': exp.get('duration', ''),
                'source': 'experience'
            }
            all_projects.append(exp_project)
        
        return all_projects    
    
    @staticmethod
    def _normalize_title(text):
        """Normalize text for strict comparison: lowercase, remove whitespace and punctuation."""
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
    
    def enhance_project_description_car(self, project: Dict, job_keywords: Set[str]) -> str:
        """Enhance project description using CAR strategy with job description keywords."""
        keywords = ", ".join(list(job_keywords)[:8])  # Limit to 8 keywords for better coverage
        original_description = project.get('description', '').strip()
        
        if not original_description:
            return original_description
            
        prompt = f"""You're a resume writing assistant. Rewrite the given project description into 6–8 **concise**, **to-the-point**, **easy-to-read sentences** using the CAR (Cause, Action, Result) strategy. Your goal is to:

- Maintain accuracy — do not hallucinate or exaggerate.
- Use provided **keywords** from the job description whenever applicable.
- Avoid fluff and background info — focus on **what was done and why it mattered**.
- Write each sentence as a **standalone impact point** suitable for resume or LinkedIn.
- **CRITICAL: Do NOT use any bullet points, symbols, dashes, arrows, or formatting markers. Write ONLY plain, direct sentences separated by line breaks.**
- **Do NOT use any markdown formatting (no **, *, _, etc.) or blank lines. Output only plain text sentences.**
- **Keep each sentence extremely concise and clear to the point.**
- If results or metrics are not given, **do not make them up**.
- Use clear, active language and relevant technical terminology.

---

**Input**
Project Description: {original_description}
Job Description Keywords: {keywords}

---

**Output**
6–8 clean, CAR-style resume points. Each should be 1–2 lines max, use keywords where appropriate, and communicate tangible work or outcomes clearly."""
        
        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                response_format={"type": "text"}
            )
            enhanced_description = response.choices[0].message.content.strip()
            
            # Ensure we return something useful even if the response is empty
            if not enhanced_description or len(enhanced_description) < 20:
                return original_description
                
            return enhanced_description
            
        except Exception as e:
            print(f"Error enhancing project description: {str(e)}")
            return original_description
    


    def select_relevant_projects(self, all_projects: list, job_keywords: Set[str], max_projects: int = 3) -> list:
        """
        Selects the most relevant projects using an LLM for contextual understanding.

        This function asks an LLM to act as a technical recruiter, analyzing all projects
        against the job keywords to find the best matches. If no projects are relevant,
        it identifies the most impressive ones overall.

        If the LLM call fails, it falls back to the original, robust algorithmic scoring method.
        """
        if not all_projects:
            return []

        try:
            # --- 1. Format Projects for the LLM ---
            # We create a simple, readable list for the prompt, giving each project a unique ID.
            formatted_projects = []
            id_to_project_map = {}
            for i, proj in enumerate(all_projects):
                project_id = f"Project{i+1}"
                id_to_project_map[project_id] = proj
                
                title = proj.get('title', 'No Title')
                description = proj.get('description', 'No Description')
                technologies = ', '.join(proj.get('technologies', []))
                
                formatted_projects.append(
                    f"ID: {project_id}\n"
                    f"Title: {title}\n"
                    f"Description: {description}\n"
                    f"Technologies: {technologies}\n"
                    "---"
                )

            projects_context = "\n".join(formatted_projects)

            # --- 2. Create the Prompt ---
            # The prompt clearly defines the AI's role, task, and rules.
            prompt = f"""You are an expert technical recruiter. Your task is to analyze a candidate's projects and select the top {max_projects} most relevant ones for a job defined by the following keywords.

    **Job Keywords:** {', '.join(job_keywords)}

    **Candidate's Projects:**
    {projects_context}

    **Instructions and Rules:**
    1.  **Primary Goal:** First, identify the projects that are most relevant to the **Job Keywords**. Your selection should be based on the project's description, technologies, and overall goal.
    2.  **Fallback Goal:** If NONE of the projects seem relevant to the keywords, then select the top {max_projects} projects that are the most technically complex, impressive, or well-described overall.
    3.  **Deduplication:** Do not select projects that appear to be duplicates or describe the same work.
    4.  **Output Format:** Your response MUST be a JSON object containing a single key "selected_project_ids", which is a list of the string IDs of your chosen projects. For example: {{"selected_project_ids": ["Project2", "Project5"]}}

    Analyze the projects and return the JSON with your selections."""

            # --- 3. Call the LLM and Process the Response ---
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Low temperature for analytical, deterministic tasks
                response_format={"type": "json_object"}
            )

            selected_ids_json = json.loads(response.choices[0].message.content)
            selected_ids = selected_ids_json.get("selected_project_ids", [])
            
            # Map the selected IDs back to the original project objects
            relevant_projects = [id_to_project_map[pid] for pid in selected_ids if pid in id_to_project_map]
            
            if not relevant_projects:
                raise ValueError("LLM returned no relevant projects. Triggering fallback.")

            return relevant_projects[:max_projects]

        except Exception as e:
            # --- 4. Algorithmic Fallback ---
            # If the LLM fails for any reason, we fall back to the original, reliable method.
            print(f"LLM-based project selection failed: {e}. Falling back to algorithmic method.", file=sys.stderr)
            
            keywords_lower = {k.lower() for k in job_keywords}
            scored_projects = []

            for proj in all_projects:
                text = (proj.get('title', '') + ' ' + proj.get('description', '')).lower()
                score = 0
                for k in keywords_lower:
                    if k in text:
                        score += 1
                    else:
                        for word in text.split():
                            if difflib.SequenceMatcher(None, k, word).ratio() >= 0.8:
                                score += 1
                                break
                
                desc_len = len(proj.get('description', ''))
                scored_projects.append((score, desc_len, proj))

            scored_projects.sort(key=lambda x: (x[0], x[1]), reverse=True)
            
            # Select all projects with a score > 0, or the top projects by length if none have a score
            top_projects = [proj for score, _, proj in scored_projects if score > 0]
            if not top_projects:
                top_projects = [proj for _, _, proj in scored_projects]

            # Deduplicate results
            deduped = []
            seen = set()
            for proj in top_projects:
                # Use a normalized title for deduplication
                normalized_title = ''.join(e for e in proj.get('title', '').lower() if e.isalnum())
                if normalized_title not in seen:
                    deduped.append(proj)
                    seen.add(normalized_title)

            return deduped[:max_projects]
        
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
    
    def _find_matching_keywords(self, job_keywords: Set[str], original_skills: list, candidate_text: str) -> list:
        """Find JD keywords that the candidate actually demonstrates in their background."""
        matching_keywords = []
        original_skills_lower = {skill.lower() for skill in original_skills}
        
        for keyword in job_keywords:
            keyword_lower = keyword.lower()
            
            # Skip if already in original skills
            if keyword_lower in original_skills_lower:
                continue
            
            # Check if keyword appears in candidate's projects, experience, etc.
            if keyword_lower in candidate_text:
                matching_keywords.append(keyword)
        
        # Limit to top 3-5 most relevant matching keywords to avoid skill inflation
        return matching_keywords[:5]
    
    def retailor_resume_with_jd(self, original_resume):
        safe_resume = self.convert_objectid_to_str(original_resume)
        job_keywords = set(safe_resume.get('keywords', []))

        all_projects = self.extract_all_projects(safe_resume)
        relevant_projects = self.select_relevant_projects(all_projects, job_keywords)

        enhanced_projects = []
        for proj in relevant_projects:
            enhanced_title = self.universal_enhance_project_title(proj)
            proj_copy = proj.copy()
            proj_copy['title'] = enhanced_title

            if job_keywords:
                enhanced_desc = self.enhance_project_description_car(proj, job_keywords)
                proj_copy['description'] = enhanced_desc

            enhanced_projects.append(proj_copy)

        safe_resume['projects'] = enhanced_projects

        if job_keywords:
            safe_resume["title"] = self.generate_tailored_title(safe_resume, job_keywords)
            safe_resume["summary"] = self.generate_professional_summary(safe_resume, job_keywords)

            original_skills = list(safe_resume.get("skills", []))
            candidate_text = self._extract_candidate_text(safe_resume)
            matching_keywords = self._find_matching_keywords(job_keywords, original_skills, candidate_text)

            job_keywords_lower = {k.lower() for k in job_keywords}
            original_skills_lower = {s.lower(): s for s in original_skills}
            matching_skills = [original_skills_lower[k] for k in job_keywords_lower if k in original_skills_lower]
            remaining_skills = [s for s in original_skills if s.lower() not in job_keywords_lower]

            prioritized_skills = matching_skills + matching_keywords + remaining_skills

            # Ensure all skills are strings and not None or empty, and handle non-string types robustly
            def safe_skill(skill):
                return skill is not None and str(skill).strip() != ""
            final_skills = [str(skill) for skill in prioritized_skills if safe_skill(skill)]
            safe_resume["skills"] = final_skills[:18]

        # ✅ Remove 'keywords' field before returning
        safe_resume.pop("keywords", None)


        # Build the final cleaned resume with only the requested fields
        final_resume = {
            "name": safe_resume.get("name", ""),
            "title": safe_resume.get("title", ""),
            "summary": safe_resume.get("summary", ""),
            "education": safe_resume.get("education", []),
            "skills": safe_resume.get("skills", []),
            "certifications": safe_resume.get("certifications", []),
            "projects": safe_resume.get("projects", [])
        }
        return final_resume

    def convert_objectid_to_str(self, obj):
        if isinstance(obj, dict):
            return {k: self.convert_objectid_to_str(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.convert_objectid_to_str(i) for i in obj]
        elif hasattr(obj, '__class__') and obj.__class__.__name__ == "ObjectId":
            return str(obj)
        else:
            return obj

def main():
    # Read from stdin (flowfile content)
    input_json = sys.stdin.read()
    try:
        resume_data = json.loads(input_json)
    except Exception as e:
        print(json.dumps({"error": f"Invalid JSON input: {str(e)}"}))
        return

    azure_config = {
            "api_key": os.environ.get('OPENAI_API_KEY'),
            "api_version": "2024-02-01",
            "endpoint": "https://resumeparser-dev.openai.azure.com/",
            "deployment": "gpt4o-mini"
        }

    retailor = ResumeRetailorWithJD(azure_config)

    try:
        retailored_resume = retailor.retailor_resume_with_jd(resume_data)
        print(json.dumps(retailored_resume))  # Only print the final resume
    except Exception as e:
        print(json.dumps({"error": f"Failed to retailor resume: {str(e)}"}))

if __name__ == "__main__":
    main()
