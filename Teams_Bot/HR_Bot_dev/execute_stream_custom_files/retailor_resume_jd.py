import sys
import json
from typing import List, Dict, Set, Tuple
import difflib
import string
from openai import AzureOpenAI
import os
from datetime import datetime

class ResumeRetailorWithJD:
    def __init__(self, azure_config: Dict[str, str]):

        self.client = AzureOpenAI(
            api_key=azure_config.get('api_key'),
            api_version=azure_config.get('api_version'),
            azure_endpoint=azure_config.get('endpoint')
        )
        self.deployment_name = azure_config.get('deployment')
        self.input_cost_per_1k = 0.000165
        self.output_cost_per_1k = 0.000660

    def log_llm_usage(self, response, prompt_type):
        timestamp = datetime.now().isoformat()
        try:
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
    
    def _extract_candidate_text(self, candidate: dict) -> str:
        """
        Extracts all relevant text from the candidate profile for keyword matching.
        """
        text_parts = []
        text_parts.append(candidate.get("summary", ""))
        text_parts.append(candidate.get("title", ""))
        for skill in candidate.get("skills", []):
            text_parts.append(str(skill))
        for proj in candidate.get("projects", []):
            text_parts.append(proj.get("title", ""))
            text_parts.append(proj.get("description", ""))
        for exp in candidate.get("experience", []):
            text_parts.append(exp.get("title", ""))
            text_parts.append(exp.get("description", ""))
        return " ".join(text_parts)
    
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

        # Use a placeholder if the original title is missing
        if not original_title:
            original_title = "Untitled Technical Project"

        # Prompt for LLM to generate a superior project title
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
            self.log_llm_usage(response, "project_title")
            enhanced_title = response.choices[0].message.content.strip().strip('"\'')

            # Fallback if LLM fails to produce a new or valid title
            is_same_title = self._normalize_title(enhanced_title) == self._normalize_title(original_title)
            if not enhanced_title or is_same_title:
                # Create a simple, guaranteed-different title as a fallback
                return f"Optimized: {original_title}"

            return enhanced_title

        except Exception as e:
            print(f"Error enhancing project title with LLM: {str(e)}", file=sys.stderr)
            # Fallback: Always return the original title if LLM fails
            return original_title
    
    def enhance_project_description_car(self, project: Dict, job_keywords: Set[str]) -> str:
        """Enhance project description using a flexible CARS model with varied hooks, vocabulary, and keyword highlighting."""
        keywords = ", ".join(list(job_keywords)[:8])
        original_description = project.get('description', '').strip()
        
        if not original_description:
            return ""

        prompt = f"""
    You are an expert resume strategist, transforming project descriptions into compelling, high-impact narratives that capture recruiter attention. Your primary tools are the CARS framework (Context, Action, Result, Skills) and varied narrative structures.

    **--- Narrative Hooks: Choose the MOST Impactful Opening ---**
    To create variety, you MUST begin each project description with one of the following hooks. Select the one that best fits the project's details.

    1.  **Action-First Hook:** Lead with the primary action or technology. (e.g., "Engineered a scalable **data pipeline**...")
    2.  **Result-First Hook:** Start with the most impressive outcome. (e.g., "Reduced manual data entry by 90%...")
    3.  **Context-First Hook (The Challenge):** Open by stating the business problem. (e.g., "Addressed a critical bottleneck in financial reporting...")

    **--- Core Components to Include ---**
    After the hook, weave in the remaining CARS components: Context, Action, Result, and Skills (by integrating `Job Keywords`).

    **--- Key Input ---**
    *   **Original Project Description:** "{original_description}"
    *   **Target Job Keywords:** "{keywords}"

    **--- CRITICAL OUTPUT REQUIREMENTS ---**
    1.  **Varied Vocabulary (NEW RULE):** Do NOT start multiple project descriptions with the same verb. Vary your sentence starters and action verbs to keep the resume engaging. Use a diverse range of powerful verbs like:
        *   **For Action:** Architected, Engineered, Developed, Implemented, Refactored, Optimized, Led, Designed, Overhauled, Standardized.
        *   **For Results:** Accelerated, Reduced, Increased, Improved, Streamlined, Eliminated, Enhanced, Solidified, Unlocked.
    2.  **Keyword Highlighting:** When a word from the `Target Job Keywords` is used, you **MUST** make it bold using double asterisks. Example: `**Python**`.
    3.  **Format:** A single, continuous paragraph of 5-7 sentences. **No bullet points or dashes.**
    4.  **Accuracy:** Do not invent facts or metrics. If a result is not stated, describe the functional improvement (e.g., "enabled real-time analytics," "improved system scalability").
    5.  **Tone:** Professional, confident, and results-focused.

    **--- High-Quality Example (Using a Result-First Hook) ---**
    *   **Original Description Example:** "I made a tool to get data from PDFs for the finance team. It used an OCR library and Python to read the files and put them into the database."
    *   **Job Keywords Example:** "Data Pipeline, Automation, Python, SQL"
    *   **IDEAL REWRITTEN OUTPUT:**
        "Reduced financial reporting errors to near-zero by developing a high-accuracy document parsing engine. Architected a fully automated **data pipeline** using **Python** and advanced OCR libraries to replace a manual, error-prone workflow. Engineered a robust data validation module and integrated the system with a **SQL** database, ensuring 99.9% data integrity. This **automation** solution empowered the finance team with real-time analytics capabilities that were previously impossible."

    **--- Now, apply this exact methodology to the provided "Key Input" and generate the rewritten description. ---**
    """
        
        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[{"role": "user", "content": prompt}],
        # Encourage vocabulary variety in LLM output
                temperature=0.4, 
                response_format={"type": "text"}
            )
            self.log_llm_usage(response, "project_description_car_final")
            enhanced_description = response.choices[0].message.content.strip()
            
            if not enhanced_description or len(enhanced_description) < 20:
                return original_description
            # Remove all '**' markers for plain text output
            enhanced_description = enhanced_description.replace('**', '')
            return enhanced_description
        except Exception as e:
            print(f"Error enhancing project description: {str(e)}", file=sys.stderr)
            return original_description
        
    def select_relevant_projects(self, all_projects: list, job_keywords: Set[str], max_projects: int = 3) -> list:
        """
        Selects the most relevant projects using an LLM for contextual understanding.
        
        This function asks an LLM to act as a strategic talent partner, analyzing all projects
        against the job keywords to find the best matches based on a nuanced evaluation framework.
        If the LLM call fails, it falls back to a robust algorithmic scoring method.
        """
        if not all_projects:
            return []

        try:
        # Format projects for LLM prompt
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

            # Create prompt for LLM to evaluate project relevance
            prompt = f"""
    You are a senior technical recruiter and talent strategist. Your goal is to identify the candidate's projects that best demonstrate their potential for a specific role, even if the connection isn't obvious. You are looking for the *best fit*, not a perfect keyword match.

    **Target Job Keywords:** {', '.join(job_keywords)}

    **Candidate's Projects:**
    {projects_context}

    **Your Task:** Select the top {max_projects} projects that are most relevant to the job keywords, following the evaluation criteria below.

    **--- Evaluation Criteria ---**
    You must evaluate relevance in the following order of priority:

    1.  **High Relevance (Direct Match):**
        *   The project's title, description, or technologies explicitly contain the job keywords.
        *   Example: Job keyword is "API Development," and a project is titled "RESTful API for E-commerce."

    2.  **Medium Relevance (Conceptual or Skill Match):**
        *   The project uses different technologies to solve a similar *type* of problem. This shows adaptability.
        *   Example: Job keyword is "AWS Lambda," but a project uses "Google Cloud Functions." Both are serverless computing and this project is highly relevant.
        *   The project demonstrates a core *skill* from the keywords, even if the project's domain is different.
        *   Example: Job keyword is "data analysis," and the project involves "Statistical Analysis of Sports Metrics." The skill is transferable and relevant.

    3.  **Low Relevance:**
        *   The project is in a completely unrelated domain and uses unrelated technology. Avoid selecting these unless no High or Medium relevance projects exist.

    **--- Decision Rules ---**
    1.  **Prioritize Nuance:** Your primary goal is to find projects with **High** or **Medium** relevance. Do not be overly harsh; value conceptual and skill-based matches.
    2.  **Tie-Breaking:** If you find more than {max_projects} relevant projects, select the ones that appear most technically complex, have the biggest business impact, or are described in the most detail.
    3.  **Fallback Plan:** If you find NO High or Medium relevance projects, use the "Tie-Breaking" rule on the entire list to select the {max_projects} most impressive projects overall.
    4.  **No Duplicates:** Do not select projects that describe the same work.

    **--- Output Format ---**
    Your response MUST be a valid JSON object with a single key, "selected_project_ids", containing a list of the chosen project ID strings.
    Example: {{"selected_project_ids": ["Project2", "Project5"]}}
    """

            # Call LLM and process response
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant designed to output JSON, strictly following the user's formatting rules."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            self.log_llm_usage(response, "project_selection")
            selected_ids_json = json.loads(response.choices[0].message.content)
            selected_ids = selected_ids_json.get("selected_project_ids", [])
            
            relevant_projects = [id_to_project_map[pid] for pid in selected_ids if pid in id_to_project_map]
            
            if not relevant_projects:
                raise ValueError("LLM returned no relevant projects. Triggering fallback.")

            return relevant_projects[:max_projects]

        except Exception as e:
            # Fallback to algorithmic method if LLM fails
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
            
            top_projects = [proj for score, _, proj in scored_projects if score > 0]
            if not top_projects:
                top_projects = [proj for _, _, proj in scored_projects]

            deduped = []
            seen = set()
            for proj in top_projects:
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
            safe_resume["summary"] = self.generate_professional_summary(safe_resume)

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

        # Remove 'keywords' field before returning
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


def main():
    # Redirect stderr to log file for error tracking
    original_stderr = sys.stderr
    log_file_path = "/home/nifi/nifi2/users/kushagra/HR_Teams_Bot_Dev/llm_usage.log"
    try:
        with open(log_file_path, 'a') as log_file:
            sys.stderr = log_file

            input_json = sys.stdin.read()
            try:
                resume_data = json.loads(input_json)
            except Exception as e:
                print(json.dumps({"error": f"Invalid JSON input: {str(e)}"}), file=sys.stderr)
                sys.exit(1)

            azure_config = {
                "api_key": os.getenv("AZURE_API_KEY"),
                "api_version": os.getenv("AZURE_API_VERSION"),
                "endpoint": os.getenv("AZURE_ENDPOINT"),
                "deployment": os.getenv("AZURE_DEPLOYMENT")
            }

            retailor = ResumeRetailorWithJD(azure_config)

            try:
                retailored_resume = retailor.retailor_resume_with_jd(resume_data)
                print(json.dumps(retailored_resume))
            except Exception as e:
                error_json = json.dumps({"error": f"Failed to retailor resume: {str(e)}"})
                print(error_json)  # Always print error to stdout for downstream flowfile
                print(error_json, file=sys.stderr)
                sys.exit(1)
    finally:
        sys.stderr = original_stderr
    # Restore original stderr

if __name__ == "__main__":
    main()
