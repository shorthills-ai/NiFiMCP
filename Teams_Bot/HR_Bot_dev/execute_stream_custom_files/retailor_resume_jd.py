import sys
import json
from typing import List, Dict, Set, Tuple
import difflib
import string
from openai import AzureOpenAI
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv( )

# Centralized env configuration
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

class ResumeRetailorWithJD:
    def __init__(self):
        self.client = AzureOpenAI(
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT
        )
        self.deployment_name = AZURE_OPENAI_DEPLOYMENT
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
    
    def _determine_industry_llm(self, company: str, description: str) -> str:
        """
        Use LLM to determine the industry based on company name and description.
        Returns the industry name or empty string if cannot determine.
        """
        prompt = f"""You are an expert business analyst specializing in industry classification. Your task is to identify the primary industry of a company based on its name and description.

                    **Company Information:**
                    - Company Name: "{company}"
                    - Description: "{description}"

                    **Instructions:**
                    1. Analyze the company name and description to determine the primary industry.
                    2. Consider both explicit mentions and contextual clues.
                    3. Return ONLY the industry name in Title Case (e.g., "Finance", "Healthcare", "Technology").
                    4. If the industry is unclear or ambiguous, return "Unknown".
                    5. Use standard industry categories like: Finance, Healthcare, Technology, Retail, Manufacturing, Education, Consulting, Government, Nonprofit, Media, Real Estate, Energy, Transportation, Hospitality, Legal, etc.

                    **Examples:**
                    - Company: "JPMorgan Chase", Description: "Financial services and banking" → "Finance"
                    - Company: "Mayo Clinic", Description: "Healthcare and medical services" → "Healthcare"
                    - Company: "Google", Description: "Technology and software development" → "Technology"
                    - Company: "Walmart", Description: "Retail and e-commerce" → "Retail"

                    Return the industry name:"""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are an expert business analyst specializing in industry classification."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "text"}
            )
            self.log_llm_usage(response, "industry_detection")
            industry = response.choices[0].message.content.strip().strip('"\'')
            
            # Validate the response
            if industry and industry.lower() not in ['unknown', 'unclear', 'ambiguous', '']:
                return industry
            return ""
            
        except Exception as e:
            print(f"Error detecting industry with LLM: {str(e)}", file=sys.stderr)
            return ""

    def _determine_industry_fallback(self, company: str, description: str) -> str:
        """
        Fallback method using hardcoded keywords to determine industry.
        Returns the industry name or empty string if cannot determine.
        """
        # Convert to lowercase for easier matching
        company_lower = company.lower()
        description_lower = description.lower()
        combined_text = f"{company_lower} {description_lower}"
        
        # Industry keywords mapping
        industry_keywords = {
            'finance': ['bank', 'financial', 'investment', 'credit', 'insurance', 'wealth', 'capital', 'trading', 'fund', 'asset', 'mortgage', 'loan'],
            'healthcare': ['hospital', 'medical', 'health', 'pharmaceutical', 'biotech', 'clinical', 'patient', 'doctor', 'nurse', 'therapy', 'diagnostic'],
            'technology': ['tech', 'software', 'ai', 'machine learning', 'data', 'cloud', 'digital', 'platform', 'app', 'system', 'development'],
            'retail': ['retail', 'ecommerce', 'shopping', 'store', 'merchant', 'commerce', 'marketplace', 'sales', 'customer'],
            'manufacturing': ['manufacturing', 'factory', 'production', 'industrial', 'automotive', 'aerospace', 'chemical', 'materials'],
            'education': ['university', 'college', 'school', 'education', 'learning', 'academic', 'research', 'student'],
            'consulting': ['consulting', 'advisory', 'strategy', 'management', 'professional services', 'business services'],
            'government': ['government', 'public', 'federal', 'state', 'municipal', 'agency', 'department'],
            'nonprofit': ['nonprofit', 'charity', 'foundation', 'ngo', 'volunteer', 'social impact'],
            'media': ['media', 'entertainment', 'publishing', 'broadcasting', 'advertising', 'marketing', 'content'],
            'real_estate': ['real estate', 'property', 'construction', 'development', 'architecture', 'building'],
            'energy': ['energy', 'oil', 'gas', 'renewable', 'solar', 'wind', 'power', 'utility'],
            'transportation': ['transportation', 'logistics', 'shipping', 'delivery', 'freight', 'supply chain']
        }
        
        # Check for industry matches - prioritize more specific matches
        # First check for exact company name matches that might indicate industry
        company_words = company_lower.split()
        for word in company_words:
            if word in ['bank', 'clinic', 'hospital', 'university', 'college']:
                if word in ['bank']:
                    return "Finance"
                elif word in ['clinic', 'hospital']:
                    return "Healthcare"
                elif word in ['university', 'college']:
                    return "Education"
        
        # Then check for keyword matches in the combined text
        for industry, keywords in industry_keywords.items():
            for keyword in keywords:
                if keyword in combined_text:
                    return industry.replace('_', ' ').title()
        
        return ""

    def _determine_industry(self, company: str, description: str) -> str:
        """
        Determine the industry using LLM first, with hardcoded fallback.
        Returns the industry name or empty string if cannot determine.
        """
        # Try LLM first
        industry = self._determine_industry_llm(company, description)
        
        # If LLM fails or returns empty, use fallback
        if not industry:
            industry = self._determine_industry_fallback(company, description)
        
        return industry
    
    def universal_enhance_project_title(self, project: Dict) -> str:

        original_title = project.get('title', '').strip()
        description = project.get('description', '')
        technologies = project.get('technologies', [])
        company = project.get('company', '')
        source = project.get('source', '')

        # If the original title is missing, create a placeholder to guide the LLM
        if not original_title:
            original_title = "Untitled Technical Project"

        # Determine if this is a work experience project and get industry info
        is_work_experience = source == 'experience'
        industry_suffix = ""
        
        if is_work_experience and company:
            # Determine industry from company name or description
            industry = self._determine_industry(company, description)
            if industry:
                industry_suffix = f" - {industry}"

        # This enhanced prompt gives the LLM clearer instructions and context,
        # empowering it to create a superior title based on the project's substance.
        prompt = f"""You are an expert resume writer. Your task is to rewrite a project title to be specific, impactful, and professional in exactly 5 to 7 words not more than that. It should be a single line and not more than 7 words. It should be specific to the project and not hallucinate.

    **Project Context:**
    - **Original Title:** "{original_title}"
    - **Description:** "{description}"
    - **Technologies Used:** "{', '.join(technologies) if technologies else 'Not specified'}"
    - **Company:** "{company}"
    - **Source:** {"Work Experience" if is_work_experience else "Personal Project"}

    **CRITICAL INSTRUCTIONS:**
    1.  **Create a NEW Title:** Your primary goal is to generate a title that is fundamentally different from the original and is more professional and impactful. DO NOT simply rephrase the original title.
    2.  **Focus on the Achievement:** Analyze the description to understand what was built, solved, or created. The title should reflect this outcome (e.g., "Automated Data Pipeline," "Scalable E-commerce Platform," "Real-time Chat Application").
    3.  **Lead with Technology (If Applicable):** If a key technology is central to the project, use it to frame the title (e.g., "Python-Based API," "React-Powered Dashboard").
    4.  **Be Specific and Professional:** Avoid generic titles. Make it sound like a real-world project.
    5.  **Industry Context (Work Experience Only):** If this is work experience, consider the industry context but DO NOT add industry suffix - that will be added automatically.
    6.  **Return ONLY the new title:** Your response must be a single line containing the title and nothing else.

    **Examples of Strong Transformations:**
    - Original: "My E-commerce Site" -> New: "Full-Stack E-commerce Platform with Stripe Integration"
    - Original: "Data Project" -> New: "Python-Driven ETL Pipeline for Sales Analytics"
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

            # Safety Check: If the LLM fails to produce a new or valid title,
            # programmatically create a different one without calling the old helper function.
            is_same_title = self._normalize_title(enhanced_title) == self._normalize_title(original_title)
            if not enhanced_title or is_same_title:
                # Create a simple, guaranteed-different title as a fallback
                enhanced_title = f"Optimized: {original_title}"

            # Add industry suffix for work experience projects
            if is_work_experience and industry_suffix:
                enhanced_title = f"{enhanced_title}{industry_suffix}"

            return enhanced_title

        except Exception as e:
            print(f"Error enhancing project title with LLM: {str(e)}", file=sys.stderr)
            # Fallback: Always return the original title if LLM fails
            fallback_title = original_title
            
            # Add industry suffix for work experience projects even in fallback
            if is_work_experience and industry_suffix:
                fallback_title = f"{fallback_title}{industry_suffix}"
                
            return fallback_title
    
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
            enhanced_description = response.choices[0].message.content.strip().strip('"\'')
            
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
            title = response.choices[0].message.content.strip().strip('"\'')
            return title if title else candidate.get('title', '')
        except Exception as e:
            print(f"Error generating job title: {str(e)}", file=sys.stderr)
            # Fallback: Always return the original title if LLM fails
            return candidate.get('title', '')

    def generate_professional_summary(self, candidate: Dict) -> str:
        """
        Generates a concise, professional summary (3-4 lines) in a neutral, impactful style,
        avoiding technical jargon and focusing on the candidate's overall value.
        """
        experience_titles = [exp.get('title') for exp in candidate.get('experience', []) if exp.get('title')]
        experience_summary = f"Career path includes roles such as: {', '.join(experience_titles)}." if experience_titles else ""
        skills_summary = ', '.join([str(s) for s in candidate.get('skills', [])[:10] if s]) # Limit to 10 key skills

        prompt = f"""
        As an expert resume writer, create a 3-4 sentence professional summary that is clear, concise, and compelling.
        Focus on the candidate's professional identity and key strengths, avoiding overly technical terms and detailed metrics.

        **Candidate Information:**
        - **Professional Title:** {candidate.get('title', 'N/A')}
        - **Years of Experience:** {candidate.get('years_experience', 'N/A')}
        - **Key Skills:** {skills_summary}
        - **Past Roles:** {experience_summary}

        **Guidelines:**

        1.  **Keep it Simple and Direct:** Use clear and straightforward language. The summary should be easy for anyone to understand, not just a technical hiring manager.

        2.  **Focus on the Person:** Describe the candidate's professional profile. Instead of listing many technologies, describe the type of professional they are.
            *   **Instead of:** "Proficient in Python, Flask, FastAPI, and LangChain..."
            *   **Aim for:** "A technology professional with a background in developing and implementing software solutions."

        3.  **Summarize, Don't List:**
            *   **Sentence 1: Introduction.** Start with the professional title and years of experience to establish their identity.
            *   **Sentence 2: Core Strengths.** Mention 2-3 key areas of expertise in broad terms (e.g., "skilled in project management and strategic planning").
            *   **Sentence 3: Professional Attributes.** Highlight key personal attributes or a notable career achievement in a non-technical way (e.g., "Known for strong problem-solving skills and a collaborative approach" or "Successfully led key projects from concept to completion").
            *   **Sentence 4 (Optional): Career Goal.** If applicable, add a forward-looking statement about their career interests.

        4.  **Avoid Jargon and Metrics:** Do not use highly technical terms or specific performance metrics. The goal is a high-level, readable summary.

        **Example Output Style:**

        "A seasoned Project Manager with over 10 years of experience in the tech industry. Skilled in leading cross-functional teams and managing complex project lifecycles. Recognized for driving process improvements and consistently delivering projects on time. A dedicated professional committed to achieving organizational goals."

        Please generate a summary based on these guidelines.
        """

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
            summary = response.choices[0].message.content.strip().strip('"\'')
            
            # ✅ CORRECTED LOGIC: Only fallback if the summary is completely empty.
            if not summary:
                return (
                    f"Professional background includes roles such as {', '.join(experience_titles)}. "
                    f"Demonstrated expertise in {skills_summary}. "
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
    
    def _intelligently_filter_skills(self, original_skills: list, job_keywords: Set[str], candidate: Dict) -> list:
        """
        Intelligently filter and prioritize skills using LLM to select the most relevant ones.
        Returns a curated list of 12-15 most relevant skills.
        """
        if not original_skills or len(original_skills) <= 20:
            return original_skills  # No filtering needed if already small enough
        
        # Extract candidate context for LLM analysis
        experience_summary = []
        for exp in candidate.get('experience', []):
            experience_summary.append(f"- {exp.get('title', '')} at {exp.get('company', '')}: {exp.get('description', '')[:200]}")
        
        project_summary = []
        for proj in candidate.get('projects', []):
            project_summary.append(f"- {proj.get('title', '')}: {proj.get('description', '')[:200]}")
        
        candidate_context = f"""
        **Professional Title:** {candidate.get('title', 'N/A')}
        **Years of Experience:** {candidate.get('years_experience', 'N/A')}
        
        **Work Experience:**
        {chr(10).join(experience_summary) if experience_summary else 'None provided'}
        
        **Key Projects:**
        {chr(10).join(project_summary) if project_summary else 'None provided'}
        """
        
        job_keywords_str = ', '.join(list(job_keywords)[:10])  # Limit to top 10 keywords
        all_skills_str = ', '.join(original_skills)
        
        prompt = f"""
        You are an expert technical recruiter and resume strategist. Your task is to intelligently select the most relevant skills from a candidate's skill list based on their background and the job requirements.

        **Candidate Profile:**
        {candidate_context}

        **Job Keywords/Requirements:**
        {job_keywords_str}

        **All Available Skills:**
        {all_skills_str}

        **Selection Criteria (in order of priority):**
        1. **Direct Job Match:** Skills that directly match the job keywords
        2. **Project Relevance:** Skills demonstrated in the candidate's projects
        3. **Experience Alignment:** Skills relevant to their work experience
        4. **Technical Depth:** Core technical skills that show expertise
        5. **Industry Relevance:** Skills that are valuable in their field

        **Instructions:**
        - Select 20-25 skills maximum
        - Prioritize skills that are both in the job requirements AND demonstrated in their background
        - Include a mix of technical and soft skills if relevant
        - Avoid redundant or overly specific skills
        - Focus on skills that tell a coherent story about the candidate's capabilities

        **Return Format:**
        Return ONLY a comma-separated list of selected skills, nothing else.
        Example: "Python, JavaScript, React, AWS, Docker, Git, Agile, Leadership, Problem Solving"

        **Selected Skills:**
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are a senior technical recruiter specializing in skill assessment and resume optimization."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                response_format={"type": "text"}
            )
            self.log_llm_usage(response, "skills_filtering")
            
            selected_skills_text = response.choices[0].message.content.strip().strip('"\'')
            
            # Parse the comma-separated response
            selected_skills = [skill.strip() for skill in selected_skills_text.split(',') if skill.strip()]
            
            # Validate that all selected skills exist in the original list (case-insensitive)
            original_skills_lower = {skill.lower(): skill for skill in original_skills}
            validated_skills = []
            
            for selected_skill in selected_skills:
                # Try exact match first
                if selected_skill in original_skills:
                    validated_skills.append(selected_skill)
                # Try case-insensitive match
                elif selected_skill.lower() in original_skills_lower:
                    validated_skills.append(original_skills_lower[selected_skill.lower()])
                # Try partial match for variations
                else:
                    for original_skill in original_skills:
                        if selected_skill.lower() in original_skill.lower() or original_skill.lower() in selected_skill.lower():
                            validated_skills.append(original_skill)
                            break
            
            # Remove duplicates while preserving order
            final_skills = []
            seen = set()
            for skill in validated_skills:
                if skill.lower() not in seen:
                    final_skills.append(skill)
                    seen.add(skill.lower())
            
            # Ensure we have a reasonable number of skills
            if len(final_skills) < 15:
                # If LLM selected too few, add some original skills back
                remaining_skills = [s for s in original_skills if s.lower() not in seen]
                final_skills.extend(remaining_skills[:15 - len(final_skills)])
            elif len(final_skills) > 25:
                # If LLM selected too many, trim to 25
                final_skills = final_skills[:25]
            
            return final_skills
            
        except Exception as e:
            print(f"Error in intelligent skills filtering: {str(e)}", file=sys.stderr)
            # Fallback to original logic
            return self._fallback_skills_filtering(original_skills, job_keywords)
    
    def _fallback_skills_filtering(self, original_skills: list, job_keywords: Set[str]) -> list:
        """
        Fallback skills filtering when LLM-based filtering fails.
        Uses simple keyword matching and prioritization.
        """
        if not original_skills:
            return []
        
        # Create priority categories
        job_keywords_lower = {k.lower() for k in job_keywords}
        original_skills_lower = {s.lower(): s for s in original_skills}
        
        # Category 1: Direct job keyword matches
        direct_matches = [original_skills_lower[k] for k in job_keywords_lower if k in original_skills_lower]
        
        # Category 2: Skills that contain job keywords
        partial_matches = []
        for skill in original_skills:
            skill_lower = skill.lower()
            if any(keyword in skill_lower for keyword in job_keywords_lower):
                if skill not in direct_matches:
                    partial_matches.append(skill)
        
        # Category 3: Remaining skills
        remaining_skills = [s for s in original_skills if s not in direct_matches and s not in partial_matches]
        
        # Combine with limits
        prioritized_skills = direct_matches + partial_matches + remaining_skills
        
        # Return top 20 skills
        return prioritized_skills[:20]
    
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
            
            # Use intelligent skills filtering to select the most relevant skills
            filtered_skills = self._intelligently_filter_skills(original_skills, job_keywords, safe_resume)
            
            # Add any job keywords that aren't already in the filtered skills
            candidate_text = self._extract_candidate_text(safe_resume)
            matching_keywords = self._find_matching_keywords(job_keywords, filtered_skills, candidate_text)
            
            # Combine filtered skills with matching keywords
            final_skills = filtered_skills + matching_keywords
            
            # Ensure all skills are strings and not None or empty
            def safe_skill(skill):
                return skill is not None and str(skill).strip() != ""
            final_skills = [str(skill) for skill in final_skills if safe_skill(skill)]
            
            # Remove duplicates while preserving order
            seen = set()
            unique_skills = []
            for skill in final_skills:
                if skill.lower() not in seen:
                    unique_skills.append(skill)
                    seen.add(skill.lower())
            
            safe_resume["skills"] = unique_skills[:25]  # Limit to 25 for optimal resume length

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
    log_file_path = os.getenv("LLM_USAGE_LOG_PATH")
    try:
        with open(log_file_path, 'a') as log_file:
            sys.stderr = log_file

            input_json = sys.stdin.read()
            try:
                resume_data = json.loads(input_json)
            except Exception as e:
                print(json.dumps({"error": f"Invalid JSON input: {str(e)}"}), file=sys.stderr)
                sys.exit(1)

            retailor = ResumeRetailorWithJD()

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
