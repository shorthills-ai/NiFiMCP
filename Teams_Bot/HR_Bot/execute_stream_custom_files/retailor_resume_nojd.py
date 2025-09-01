import json
import re
import random
from typing import List, Dict, Set, Tuple
from openai import AzureOpenAI
import sys
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv(dotenv_path="/home/nifi/nifi2/HR_Bot/.env")

# Centralized env configuration
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")

class ResumeRetailorNoJD:
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
    
    def enhance_project_description_no_jd(self, project: Dict) -> str:
        """
        Enhance project description using CARS format without job keywords.
        Only enhances descriptions that are longer than 10 words.
        """
        original_description = project.get('description', '').strip()
        
        # Check if description is too short (less than 10 words)
        if not original_description or len(original_description.split()) <= 10:
            return original_description

        prompt = f"""
            You are an expert resume strategist, transforming project descriptions into compelling, high-impact narratives that capture recruiter attention. Your primary tool is the CARS framework (Context, Action, Result, Skills).

            **--- Narrative Hooks: Choose the MOST Impactful Opening ---**
            To create variety, you MUST begin each project description with one of the following hooks. Select the one that best fits the project's details.

            1.  **Action-First Hook:** Lead with the primary action or technology. (e.g., "Engineered a scalable data pipeline...")
            2.  **Result-First Hook:** Start with the most impressive outcome. (e.g., "Reduced manual data entry by 90%...")
            3.  **Context-First Hook (The Challenge):** Open by stating the business problem. (e.g., "Addressed a critical bottleneck in financial reporting...")

            **--- Core Components to Include ---**
            After the hook, weave in the remaining CARS components: Context, Action, Result, and Skills.

            **--- Key Input ---**
            *   **Original Project Description:** "{original_description}"

            **--- CRITICAL OUTPUT REQUIREMENTS ---**
            1.  **Varied Vocabulary:** Do NOT start multiple project descriptions with the same verb. Vary your sentence starters and action verbs to keep the resume engaging. Use a diverse range of powerful verbs like:
                *   **For Action:** Architected, Engineered, Developed, Implemented, Refactored, Optimized, Led, Designed, Overhauled, Standardized.
                *   **For Results:** Accelerated, Reduced, Increased, Improved, Streamlined, Eliminated, Enhanced, Solidified, Unlocked.
            2.  **Format:** A single, continuous paragraph of 5-7 sentences. **No bullet points or dashes.**
            3.  **Accuracy:** Do not invent facts or metrics. If a result is not stated, describe the functional improvement (e.g., "enabled real-time analytics," "improved system scalability").
            4.  **Tone:** Professional, confident, and results-focused.
            5.  **No Hallucination:** Base the enhancement only on the information provided in the original description.

            **--- High-Quality Example (Using a Result-First Hook) ---**
            *   **Original Description Example:** "I made a tool to get data from PDFs for the finance team. It used an OCR library and Python to read the files and put them into the database."
            *   **IDEAL REWRITTEN OUTPUT:**
                "Reduced financial reporting errors to near-zero by developing a high-accuracy document parsing engine. Architected a fully automated data pipeline using Python and advanced OCR libraries to replace a manual, error-prone workflow. Engineered a robust data validation module and integrated the system with a SQL database, ensuring 99.9% data integrity. This automation solution empowered the finance team with real-time analytics capabilities that were previously impossible."

            **--- Now, apply this exact methodology to the provided "Key Input" and generate the rewritten description. ---**
            """
                
        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4, 
                response_format={"type": "text"}
            )
            self.log_llm_usage(response, "project_description_no_jd")
            enhanced_description = response.choices[0].message.content.strip().strip('"\'')
            
            if not enhanced_description or len(enhanced_description) < 20:
                return original_description
            
            return enhanced_description
        except Exception as e:
            print(f"Error enhancing project description: {str(e)}", file=sys.stderr)
            return original_description
    
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
            title = response.choices[0].message.content.strip().strip('"\'')
            return title if title else candidate.get('title', '')
        except Exception as e:
            print(f"Error generating job title: {str(e)}", file=sys.stderr)
            # Fallback: Always return the original title if LLM fails
            return candidate.get('title', '')
    
    def _intelligently_filter_skills_no_jd(self, original_skills: list, candidate: Dict) -> list:
        """
        Intelligently filter and prioritize skills using LLM to select the most relevant ones for NoJD case.
        Returns a curated list of 12-15 most relevant skills based on candidate's background.
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
        
        all_skills_str = ', '.join(original_skills)
        
        prompt = f"""
        You are an expert technical recruiter and resume strategist. Your task is to intelligently select the most relevant skills from a candidate's skill list based on their background and professional profile.

        **Candidate Profile:**
        {candidate_context}

        **All Available Skills:**
        {all_skills_str}

        **Selection Criteria (in order of priority):**
        1. **Project Relevance:** Skills demonstrated in the candidate's projects
        2. **Experience Alignment:** Skills relevant to their work experience
        3. **Technical Depth:** Core technical skills that show expertise
        4. **Industry Relevance:** Skills that are valuable in their field
        5. **Career Progression:** Skills that support their professional growth

        **Instructions:**
        - Select 20-25 skills maximum
        - Prioritize skills that are demonstrated in their projects and experience
        - Include a mix of technical and soft skills if relevant
        - Avoid redundant or overly specific skills
        - Focus on skills that tell a coherent story about the candidate's capabilities
        - Consider the candidate's professional level and industry

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
            self.log_llm_usage(response, "skills_filtering_no_jd")
            
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
            print(f"Error in intelligent skills filtering (NoJD): {str(e)}", file=sys.stderr)
            # Fallback: return top 20 skills based on length (shorter skills first)
            return sorted(original_skills, key=len)[:20]
    
    def retailor_resume_no_jd(self, original_resume: Dict) -> Dict:
        """
        Retailor the resume without a job description:
        - Enhances all project titles (including work experience converted to projects)
        - Enhances project descriptions using CARS format (for descriptions > 10 words)
        - Generates professional summary and title
        - Maintains original skills
        """
        # Convert ObjectId to string for JSON serialization
        safe_resume = self.convert_objectid_to_str(original_resume)
        job_keywords = set(safe_resume.get('keywords', []))
        
        # Extract ALL projects from both projects and experience sections
        all_projects = self.extract_all_projects(safe_resume)
        
        # Enhance titles and descriptions for all projects (including work experience)
        enhanced_projects = []
        for proj in all_projects:
            enhanced_title = self.universal_enhance_project_title(proj)
            enhanced_description = self.enhance_project_description_no_jd(proj)
            proj_copy = proj.copy()
            proj_copy['title'] = enhanced_title
            proj_copy['description'] = enhanced_description
            enhanced_projects.append(proj_copy)
        
        # Update the resume with enhanced project titles
        safe_resume['projects'] = enhanced_projects
        
        # Generate professional title if not present
        if not safe_resume.get("title"):
            safe_resume["title"] = self.generate_tailored_title(safe_resume,job_keywords)
        
        # Always generate professional summary using LLM (original summary only used as fallback)
        safe_resume["summary"] = self.generate_professional_summary(safe_resume)
        
        # Intelligently filter skills if there are too many (more than 25)
        original_skills = list(safe_resume.get("skills", []))
        if len(original_skills) > 25:
            filtered_skills = self._intelligently_filter_skills_no_jd(original_skills, safe_resume)
            safe_resume["skills"] = filtered_skills
        # Otherwise keep original skills as they are
        
        return safe_resume

def main():

    original_stderr = sys.stderr
    log_file_path = os.getenv("LLM_USAGE_LOG_PATH")
    try:
        with open(log_file_path, 'a') as log_file:
            sys.stderr = log_file
            input_resume = json.load(sys.stdin)
            retailor = ResumeRetailorNoJD()
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
