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
        self.client = AzureOpenAI(
            api_key=azure_config["api_key"],
            api_version=azure_config["api_version"],
            azure_endpoint=azure_config["azure_endpoint"]
        )
        
        self.deployment_name = azure_config["deployment_name"]
    
  
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
    
    def _extract_main_technology(self, description: str, technologies: list) -> str:
        """Helper method to extract the main technology from project info."""
        # First check the technologies list
        if technologies:
            return technologies[0].title()
        
        # Then check the description for common technologies
        description_lower = description.lower()
        common_techs = [
            'n8n', 'python', 'javascript', 'react', 'node', 'nodejs', 'java', 'aws', 
            'mongodb', 'mysql', 'postgresql', 'docker', 'kubernetes', 'tensorflow', 
            'flask', 'django', 'angular', 'vue', 'spring', 'express', 'redis', 
            'elasticsearch', 'jenkins', 'git', 'llm', 'openai', 'chatgpt', 'gpt', 
            'azure', 'firebase', 'stripe', 'oauth', 'jwt', 'restapi', 'graphql', 
            'websocket', 'microservices', 'serverless', 'lambda', 'html', 'css', 
            'bootstrap', 'tailwind', 'nextjs', 'nuxtjs', 'svelte', 'php', 'laravel', 
            'symfony', 'ruby', 'rails', 'go', 'rust', 'swift', 'kotlin', 'flutter', 
            'dart', 'unity', 'unreal', 'blender'
        ]
        
        for tech in common_techs:
            if tech in description_lower:
                # Special case for n8n to keep it uppercase
                return 'n8n' if tech == 'n8n' else tech.title()
        
        return ""
    
    @staticmethod
    def _normalize_title(text):
        """Normalize text for strict comparison: lowercase, remove whitespace and punctuation."""
        import string
        return ''.join(c for c in text.lower() if c not in string.whitespace + string.punctuation)
    
    def universal_enhance_project_title(self, project: Dict) -> str:
        """
        UNIVERSAL function that ALWAYS enhances project titles to be skill-focused and impactful.
        Works regardless of whether JD is provided or not. Guaranteed to produce a different title.
        """
        original_title = project.get('title', '').strip()
        description = project.get('description', '')
        technologies = project.get('technologies', [])
        
        # If no original title, create a basic one
        if not original_title:
            original_title = "Technical Project"
        
        prompt = f"""You are an expert at creating impactful, skill-focused project titles. Your job is to rewrite this project title to be more professional, attention-grabbing, and technology-focused.

CRITICAL REQUIREMENTS:
- The new title MUST be different from the original title
- Highlight the main technologies/skills used in the project
- Make it professional and impactful
- Use technology prefixes when applicable (e.g., "React-Based", "Python-Powered", "n8n-Driven", "AWS-Deployed")
- Focus on what makes this project technically interesting
- Return ONLY the enhanced title, no explanations

Original Title: {original_title}
Project Description: {description}
Technologies Used: {', '.join(technologies) if technologies else 'Not specified'}

Examples of good enhanced titles:
- "n8n-Based Resume Automation Pipeline" 
- "React-Powered E-commerce Platform"
- "Python-Driven Data Analytics Dashboard"
- "AWS-Deployed Microservices Architecture"
- "MongoDB-Backed Social Media Application"
- "Full-Stack Web Application with Authentication"
- "Machine Learning-Powered Recommendation System"
- "Real-Time Chat Application with WebSocket"

Create an enhanced, skill-focused title:"""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                response_format={"type": "text"}
            )
            enhanced_title = response.choices[0].message.content.strip()
            
            # Remove any quotes if they exist
            enhanced_title = enhanced_title.strip('"\'')
            
            # Safety check: if somehow the same title is returned, force a change
            if self._normalize_title(enhanced_title) == self._normalize_title(original_title):
                # Extract main technology and create a forced enhancement
                main_tech = self._extract_main_technology(description, technologies)
                if main_tech:
                    enhanced_title = f"{main_tech}-Based {original_title}"
                else:
                    enhanced_title = f"Advanced {original_title}"
            
            return enhanced_title
            
        except Exception as e:
            print(f"Error enhancing project title: {str(e)}")
            # Robust fallback that always produces a different title
            main_tech = self._extract_main_technology(description, technologies)
            if main_tech:
                return f"{main_tech}-Based {original_title}"
            else:
                return f"Professional {original_title}"
    
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
        keywords_lower = {k.lower() for k in job_keywords}
        scored_projects = []

        def fuzzy_keyword_match(text, keywords, threshold=0.8):
            """Return number of keywords that fuzzy-match in the text."""
            text = text.lower()
            count = 0
            for k in keywords:
                # Direct substring match
                if k in text:
                    count += 1
                    continue
                # Fuzzy match: check if any word in text is similar to keyword
                words = text.split()
                for word in words:
                    if difflib.SequenceMatcher(None, k, word).ratio() >= threshold:
                        count += 1
                        break
            return count

        for proj in all_projects:
            text = (proj.get('title', '') + ' ' + proj.get('description', '')).lower()
            # Fuzzy count of keyword matches
            score = fuzzy_keyword_match(text, keywords_lower)
            desc_len = len(proj.get('description', ''))
            scored_projects.append((score, desc_len, proj))

        # Sort by score (descending), then by description length (descending)
        scored_projects.sort(key=lambda x: (x[0], x[1]), reverse=True)

        # Select top N with score > 0
        top_relevant = [proj for score, _, proj in scored_projects if score > 0][:max_projects*2]  # get more for deduplication

        if not top_relevant:
            # Fallback: top N by description length
            top_relevant = [proj for _, _, proj in scored_projects[:max_projects*2]]

        # Deduplicate similar projects (by title+description)
        deduped = []
        seen = []
        for proj in top_relevant:
            title_desc = (proj.get('title', '') + ' ' + proj.get('description', '')).lower()
            is_duplicate = False
            for s in seen:
                if difflib.SequenceMatcher(None, title_desc, s).ratio() > 0.85:
                    is_duplicate = True
                    break
            if not is_duplicate:
                deduped.append(proj)
                seen.append(title_desc)
            if len(deduped) >= max_projects:
                break
        return deduped
        
    def generate_job_specific_title(self, candidate: Dict, job_keywords: Set[str]) -> str:
        """Generate a job-specific title for the candidate based on their profile and job keywords."""
        prompt = f"""You are an expert HR professional specializing in job title creation. Create a specific, professional job title that accurately reflects the candidate's experience and aligns with the job requirements.

Rules:
- Use industry-standard job titles
- Match the candidate's actual experience level (don't overstate)
- Be specific to the role and industry
- Use ONLY information from the candidate's profile and job keywords
- Return ONLY the job title, no explanation

Candidate Profile:
- Name: {candidate.get('name', '')}
- Current Title: {candidate.get('title', '')}
- Skills: {', '.join([str(s) for s in candidate.get('skills', []) if s])}
- Projects: {json.dumps(candidate.get('projects', []), indent=2)}
- Education: {json.dumps(candidate.get('education', []), indent=2)}

Job Keywords: {', '.join(job_keywords)}

Generate a professional job title that matches their experience level and aligns with the job requirements:"""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                response_format={"type": "text"}
            )
            
            title = response.choices[0].message.content.strip()
            return title
            
        except Exception as e:
            print(f"Error generating job title: {str(e)}")
            return candidate.get('title', '')
    
    def generate_professional_summary(self, candidate: Dict, job_keywords: Set[str]) -> str:
        """Generates or enhances a professional summary aligned with job keywords."""
        existing_summary = candidate.get('summary', '').strip()
        prompt = f"""You are an expert resume writer and HR professional. Your job is to ensure the candidate's professional summary is concise (3-4 sentences), clear, and tailored to the job requirements. If a summary is provided, rewrite it to be more professional, justified, and impactful. If not, generate a new one based on the candidate's profile and job keywords.

CRITICAL RULES:
- Write in the third person, maintaining a formal and confident tone.
- The summary must be strictly based on the candidate's profile. Do not invent or exaggerate information.
- Seamlessly weave in skills and experiences that are most relevant to the provided Job Keywords.
- Highlight the candidate's key strengths and value proposition for the role.
- The summary should be 3-4 sentences, not too long, and very clear.
- Return ONLY the summary paragraph. Do not include any extra text, labels, or quotation marks.

Candidate Profile:
- Name: {candidate.get('name', '')}
- Title: {candidate.get('title', '')}
- Skills: {', '.join([str(s) for s in candidate.get('skills', []) if s])}
- Experience: {json.dumps(candidate.get('experience', []), indent=2)}
- Projects: {json.dumps(candidate.get('projects', []), indent=2)}
- Education: {json.dumps(candidate.get('education', []), indent=2)}

Job Keywords: {', '.join(job_keywords)}

Existing Summary: {existing_summary if existing_summary else 'None'}

Write or enhance the professional summary as described above:"""
        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                response_format={"type": "text"}
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error generating summary: {str(e)}")
            return existing_summary or candidate.get('summary', '')
    
    def _extract_candidate_text(self, resume: Dict) -> str:
        """Extract all text content from candidate's resume for skill matching."""
        text_parts = []
        # Add project descriptions and titles
        for proj in resume.get('projects', []):
            title = proj.get('title', '')
            if title is not None:
                text_parts.append(str(title))
            desc = proj.get('description', '')
            if desc is not None:
                text_parts.append(str(desc))
            techs = proj.get('technologies', [])
            if techs:
                text_parts.extend([str(t) for t in techs if t is not None and str(t).strip() != ''])
        # Add experience descriptions and titles
        for exp in resume.get('experience', []):
            title = exp.get('title', '')
            if title is not None:
                text_parts.append(str(title))
            pos = exp.get('position', '')
            if pos is not None:
                text_parts.append(str(pos))
            desc = exp.get('description', '')
            if desc is not None:
                text_parts.append(str(desc))
            techs = exp.get('technologies', [])
            if techs:
                text_parts.extend([str(t) for t in techs if t is not None and str(t).strip() != ''])
        # Add education information
        for edu in resume.get('education', []):
            degree = edu.get('degree', '')
            if degree is not None:
                text_parts.append(str(degree))
            inst = edu.get('institution', '')
            if inst is not None:
                text_parts.append(str(inst))
            field = edu.get('field', '')
            if field is not None:
                text_parts.append(str(field))
        # Add certifications
        for cert in resume.get('certifications', []):
            if isinstance(cert, dict):
                title = cert.get('title', '')
                if title is not None:
                    text_parts.append(str(title))
                issuer = cert.get('issuer', '')
                if issuer is not None:
                    text_parts.append(str(issuer))
            else:
                if cert is not None:
                    text_parts.append(str(cert))
        # Add summary
        summary = resume.get('summary', '')
        if summary is not None:
            text_parts.append(str(summary))
        return ' '.join(text_parts).lower()
    
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
            safe_resume["title"] = self.generate_job_specific_title(safe_resume, job_keywords)
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
        "api_key": "",
        "api_version": "2024-08-01-preview",
        "azure_endpoint": "https://us-tax-law-rag-demo.openai.azure.com/",
        "deployment_name": "gpt-4o-mini"
    }

    retailor = ResumeRetailorWithJD(azure_config)

    try:
        retailored_resume = retailor.retailor_resume_with_jd(resume_data)
        print(json.dumps(retailored_resume))  # Only print the final resume
    except Exception as e:
        print(json.dumps({"error": f"Failed to retailor resume: {str(e)}"}))

if __name__ == "__main__":
    main()
