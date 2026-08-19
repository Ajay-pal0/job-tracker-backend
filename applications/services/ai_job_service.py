import os
import json
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class AIJobClassifierService:
    """
    LLM-powered email classification and job extraction service.
    Evaluates whether an email is job-application related (applied, interview, rejection, offer),
    extracts structured attributes (company, role, status, platform, recruiter details),
    and generates AI reasoning explanations.
    Supports Google Gemini API, OpenAI API, and falls back seamlessly to rule-based regex parsing.
    """

    @classmethod
    def analyze_email_with_llm(cls, subject: str, sender: str, body: str) -> Optional[Dict[str, Any]]:
        """
        Attempts to analyze an email using configured LLM providers (Gemini or OpenAI).
        Returns a dict with structured metadata or None if LLM is unconfigured/unavailable.
        """
        gemini_api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_AI_API_KEY')
        openai_api_key = os.getenv('OPENAI_API_KEY')

        if gemini_api_key:
            res = cls._analyze_with_gemini(subject, sender, body, gemini_api_key)
            if res:
                return res

        if openai_api_key:
            res = cls._analyze_with_openai(subject, sender, body, openai_api_key)
            if res:
                return res

        return None

    @classmethod
    def _build_prompt(cls, subject: str, sender: str, body: str) -> str:
        snippet = body[:1500].strip()
        return f"""You are an intelligent AI recruitment assistant analyzing emails for a Job Application Tracking System.
Analyze the email below and determine if it is related to a job application, candidate outreach, recruiter correspondence, interview invitation, offer, or rejection.

EMAIL DETAILS:
- Subject: {subject}
- From / Sender: {sender}
- Email Body Snippet:
{snippet}

Respond ONLY with a raw valid JSON object matching this exact schema (no markdown, no extra commentary):
{{
  "is_job_related": true,
  "confidence": 0.95,
  "company_name": "Exact Company Name",
  "job_title": "Role Title",
  "status": "Applied",
  "platform": "LinkedIn",
  "recruiter_name": "Recruiter Name or empty string",
  "recruiter_email": "Recruiter Email or empty string",
  "reasoning": "Brief 1-sentence explanation of why this email is or isn't job related"
}}

VALID STATUS OPTIONS: "Applied", "Interview Scheduled", "Rejected", "Offer".
VALID PLATFORM OPTIONS: "LinkedIn", "Greenhouse", "Lever", "Workday", "Indeed", "Naukri", "Glassdoor", "Company Website", "Other".
"""

    @classmethod
    def _analyze_with_gemini(cls, subject: str, sender: str, body: str, api_key: str) -> Optional[Dict[str, Any]]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            prompt_text = cls._build_prompt(subject, sender, body)

            payload = {
                "contents": [{"parts": [{"text": prompt_text}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "response_mime_type": "application/json"
                }
            }

            response = requests.post(url, json=payload, timeout=8)
            if response.status_code == 200:
                res_data = response.json()
                text_content = res_data['candidates'][0]['content']['parts'][0]['text']
                clean_json = text_content.strip().lstrip('```json').lstrip('```').rstrip('```').strip()
                data = json.loads(clean_json)
                data['source'] = 'AI_LLM'
                return data
            else:
                logger.warning(f"Gemini API returned HTTP {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Error executing Gemini LLM analysis: {e}")

        return None

    @classmethod
    def _analyze_with_openai(cls, subject: str, sender: str, body: str, api_key: str) -> Optional[Dict[str, Any]]:
        try:
            url = "https://api.openai.com/v1/chat/completions"
            prompt_text = cls._build_prompt(subject, sender, body)

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "You are a specialized JSON-only AI assistant for job application classification."},
                    {"role": "user", "content": prompt_text}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1
            }

            response = requests.post(url, headers=headers, json=payload, timeout=8)
            if response.status_code == 200:
                res_data = response.json()
                text_content = res_data['choices'][0]['message']['content']
                data = json.loads(text_content)
                data['source'] = 'AI_LLM'
                return data
        except Exception as e:
            logger.error(f"Error executing OpenAI LLM analysis: {e}")

        return None
