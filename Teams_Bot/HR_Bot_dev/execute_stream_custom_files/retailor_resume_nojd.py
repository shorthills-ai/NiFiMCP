import json
import re
import random
from typing import List, Dict, Set, Tuple
from openai import AzureOpenAI
import sys

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
        # api_key = ""
        # api_version = "2024-08-01-preview"
        # azure_endpoint = "https://us-tax-law-rag-demo.openai.azure.com/"
        # deployment_name = "gpt-4o-mini"

        self.client = AzureOpenAI(
            api_key=azure_config["api_key"],
            api_version=azure_config["api_version"],
            azure_endpoint=azure_config["azure_endpoint"]
        )
        self.deployment_name = azure_config["deployment_name"]
    
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
                temperature=0.3,  # Slightly higher for more variety
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
            print(f"Error enhancing project title: {str(e)}", file=sys.stderr)
            # Robust fallback that always produces a different title
            main_tech = self._extract_main_technology(description, technologies)
            if main_tech:
                return f"{main_tech}-Based {original_title}"
            else:
                return f"Professional {original_title}"
    
    def generate_professional_summary(self, candidate: Dict) -> str:
        """Generates or enhances a professional summary based on candidate's profile."""
        existing_summary = candidate.get('summary', '').strip()
        prompt = f"""You are an expert resume writer and HR professional. Your job is to ensure the candidate's professional summary is concise (3-4 sentences), clear, and tailored to their background. If a summary is provided, rewrite it to be more professional, justified, and impactful. If not, generate a new one based on the candidate's profile.

CRITICAL RULES:
- Write in the third person, maintaining a formal and confident tone.
- The summary must be strictly based on the candidate's profile. Do not invent or exaggerate information.
- Highlight the candidate's key strengths and value proposition for the role.
- The summary should be 3-4 sentences, not too long, and very clear.
- Return ONLY the summary paragraph. Do not include any extra text, labels, or quotation marks.

Candidate Profile:
- Name: {candidate.get('name', '')}
- Title: {candidate.get('title', '')}
- Skills: {', '.join(candidate.get('skills', []))}
- Experience: {json.dumps(candidate.get('experience', []), indent=2)}
- Projects: {json.dumps(candidate.get('projects', []), indent=2)}
- Education: {json.dumps(candidate.get('education', []), indent=2)}

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
    
    def generate_professional_title(self, candidate: Dict) -> str:
        """Generate a professional job title based on candidate's experience and skills."""
        prompt = f"""You are an expert HR professional specializing in job title creation. Create a specific, professional job title that accurately reflects the candidate's experience level.

Rules:
- Use industry-standard job titles
- Match the candidate's actual experience level (don't overstate)
- Be specific to the role and industry
- Use ONLY information from the candidate's profile
- Return ONLY the job title, no explanation

Candidate Profile:
- Name: {candidate.get('name', '')}
- Current Title: {candidate.get('title', '')}
- Skills: {', '.join(candidate.get('skills', []))}
- Projects: {json.dumps(candidate.get('projects', []), indent=2)}
- Education: {json.dumps(candidate.get('education', []), indent=2)}

Generate a professional job title that matches their experience level:"""

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
            print(f"Error generating job title: {str(e)}", file=sys.stderr)
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
            safe_resume["title"] = self.generate_professional_title(safe_resume)
        
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
            "api_key": "",
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
