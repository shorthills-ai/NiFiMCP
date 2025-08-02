import json
import re
import random
from typing import List, Dict, Set, Tuple
from openai import AzureOpenAI
import sys
import os
from datetime import datetime

class ResumeRetailorNoJD:
    def __init__(self, azure_config: Dict[str, str]):
        """
        Initialize the resume retailor with Azure OpenAI configuration.
        Args:
            azure_config: Dictionary containing Azure OpenAI configuration
        """
        self.client = AzureOpenAI(
            api_key=azure_config.get('api_key'),
            api_version=azure_config.get('api_version'),
            azure_endpoint=azure_config.get('endpoint')
        )
        self.deployment_name = azure_config.get('deployment')
        self.input_cost_per_1k = 0.000165
        self.output_cost_per_1k = 0.000660

    def log_llm_usage(self, response, prompt_type):
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
                temperature=0.4,
                response_format={"type": "text"}
            )
            self.log_llm_usage(response, "project_title")
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
            # Fallback: Always return the original title if LLM fails
            return original_title
    


    def generate_professional_summary(self, candidate: Dict) -> str:
        """
        Always generates a professional summary (4-5 lines) in a neutral, impactful, professional style, without personal pronouns.
        """
        experience_titles = [exp.get('title') for exp in candidate.get('experience', []) if exp.get('title')]
        experience_summary = f"Career path includes roles like: {', '.join(experience_titles)}." if experience_titles else ""
        project_titles = [p.get('title') for p in candidate.get('projects', []) if p.get('title')]
        project_summary = f"Key projects include: {', '.join(project_titles)}." if project_titles else ""
        skills_summary = ', '.join([str(s) for s in candidate.get('skills', [])[:15] if s])

        prompt = f"""
        You are a top-tier executive resume writer and career strategist with over 20 years of experience in recruiting and hiring for Fortune 500 companies. Your task is to write a powerful 3–4 sentence professional summary that immediately captures a hiring manager's attention and conveys the candidate's value proposition.
        Follow these expert guidelines precisely:
        Candidate Context:
        Professional Title: {candidate.get('title', 'N/A')}
        Career Stage: {candidate.get('career_stage', 'Experienced Professional')} #(Options: Entry-Level, Mid-Career, Senior Leader, Executive, Career Changer)
        Years of Experience: {candidate.get('years_experience', 'N/A')}
        Top Skills (up to 15): {skills_summary}
        Key Roles & Experience: {experience_summary}
        Major Projects & Outcomes: {project_summary}

        1. Adaptive Writing Strategy:
        For Senior Leader/Executive: Start with a powerful statement about leadership scope or strategic impact. Emphasize budget management, team leadership, P&L responsibility, and market-level outcomes.
        For Mid-Career/Experienced Professional: Lead with years of experience and core expertise. Focus on quantifiable achievements and proven skills directly relevant to the professional title.
        For Entry-Level: Focus on academic background, key technical skills, and internship or project-based outcomes. Highlight ambition, core competencies, and a strong understanding of foundational principles.
        For Career Changer: Bridge the past and present. Start by stating the target professional title, then connect relevant skills from previous roles to the new field, emphasizing transferable achievements.

        2. Core Writing Requirements:
        Length & Structure: Exactly 3–4 sentences, each delivering a distinct and impactful point.
        Tone & Language: Use an authoritative, factual, and confident tone. Employ active-voice verbs (e.g., "architected," "spearheaded," "revitalized"). Do not use personal pronouns ("I," "me," "my").
        Content & Focus:
        Sentence 1: The Hook. Open with the candidate's professional identity, incorporating their title and years of experience (or for career changers, their target title).
        Sentence 2: The Expertise. Detail 2-3 core areas of functional expertise (e.g., "intelligent systems design," "workflow automation," "strategic AI implementation"), not just a list of technologies.
        Sentence 3: The Proof. Showcase a major achievement, quantifying it with metrics. If metrics are not available, describe the business outcome or scope of the achievement (e.g., "streamlined recruitment processes by developing a novel AI tool").
        Sentence 4: The Value & Impact. Connect the candidate's work to broader business value. Explain how their contributions have driven growth, improved processes, or supported strategic goals. Conclude with a statement of their overall capability.

        3. Accuracy & Formatting:
        Fact-Based: Do not invent facts or skills. Base the summary exclusively on the provided Candidate Context.
        Clean Output: Do not add headers, labels, or quotation marks. The output must be a single, continuous paragraph.
        
        4. Strategic Abstraction of Technical Details (New Guideline):
        Translate, Don't List: Your primary goal is to translate technical skills into business capabilities. Instead of listing specific frameworks or languages, describe what the candidate does with them.
        Instead of: "Proficient in Python, Flask, FastAPI, LangChain, and Hugging Face..."
        Aim for: "Expertise in developing and deploying scalable AI solutions and intelligent automation systems..."
        Focus on Business Problems, Not Technical Architecture: Describe projects based on the business problem they solved or the value they created.
        Instead of: "Architected an OpenAI-Enhanced Automated Resume Tailoring Pipeline integrating Microsoft Teams..."
        Aim for: "Spearheaded the development of an AI-driven talent acquisition tool that automated resume processing and enhanced candidate engagement..."
        General Principle: Emphasize the "what" (the capability) and the "why" (the business impact) over the "how" (the specific tools). A touch of technical context is good for credibility, but the focus must remain on strategic contribution."""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are a top-tier resume writer and career strategist."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                response_format={"type": "text"}
            )
            self.log_llm_usage(response, "summary")
            summary = response.choices[0].message.content.strip()
            
            # ✅ CORRECTED LOGIC: Only fallback if the summary is completely empty.
            if not summary:
                return (
                    f"Professional background includes roles such as {', '.join(experience_titles)}. "
                    f"Demonstrated expertise in {skills_summary}. "
                    f"Projects delivered: {', '.join(project_titles)}. "
                    f"Recognized for reliability and technical proficiency."
                )
            return summary
        except Exception as e:
            print(f"Error generating summary: {str(e)}", file=sys.stderr)
            # Fallback for API errors: Use candidate's original summary if available, else use hardcoded fallback
            original_summary = candidate.get('summary')
            if original_summary:
                return original_summary
            return (
                f"Professional background includes roles such as {', '.join(experience_titles)}. "
                f"Demonstrated expertise in {skills_summary}. "
                f"Projects delivered: {', '.join(project_titles)}. "
                f"Recognized for reliability and technical proficiency."
            )
        
    def generate_tailored_title(self, candidate: Dict, job_keywords: Set[str] = None) -> str:
        """
        Generates a professional job title based on the candidate's profile.
        If job_keywords are provided, it tailors the title to align with the job description.
        """
        experience_summary = [f"- {exp.get('title', '')} at {exp.get('company', '')}" for exp in candidate.get('experience', [])]
        skills_summary = ', '.join([str(s) for s in candidate.get('skills', [])[:10] if s])

        prompt_lines = [
            "Based on the following professional profile, generate a single, industry-standard job title.",
            "\n**Candidate Profile:**",
            f"- **Current/Recent Title:** {candidate.get('title', 'N/A')}",
            f"- **Key Skills:** {skills_summary}",
            "- **Experience History:**",
            *experience_summary,
        ]

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
                temperature=0.2,
                response_format={"type": "text"}
            )
            self.log_llm_usage(response, "job_title")
            title = response.choices[0].message.content.strip().strip('"')
            return title if title else candidate.get('title', '')
        except Exception as e:
            print(f"Error generating job title: {str(e)}", file=sys.stderr)
            # Fallback: Always return the original title if LLM fails
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
        
        # Always generate professional summary using LLM (original summary only used as fallback)
        safe_resume["summary"] = self.generate_professional_summary(safe_resume)
        
        return safe_resume

def main():

    original_stderr = sys.stderr
    log_file_path = "/home/nifi/nifi2/users/HR_Teams_Bot_Dev/llm_usage.log"
    try:
        with open(log_file_path, 'a') as log_file:
            sys.stderr = log_file
            azure_config = {
                "api_key": os.getenv("AZURE_API_KEY"),
                "api_version": os.getenv("AZURE_API_VERSION"),
                "endpoint": os.getenv("AZURE_ENDPOINT"),
                "deployment": os.getenv("AZURE_DEPLOYMENT")
            }
            input_resume = json.load(sys.stdin)
            retailor = ResumeRetailorNoJD(azure_config)
            retailored_resume = retailor.retailor_resume_no_jd(input_resume)
            print(json.dumps(retailored_resume, indent=2))
    except json.JSONDecodeError:
        print(json.dumps({"error": "Invalid JSON input"}), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": f"An unexpected error occurred: {str(e)}"}), file=sys.stderr)
        sys.exit(1)
    finally:
        sys.stderr = original_stderr
        


if __name__ == "__main__":
    main()
