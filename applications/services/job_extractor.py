import re
from typing import Dict, Any, Optional
from datetime import date
from .email_parser import EmailJobParser
from .ai_job_service import AIJobClassifierService

class JobExtractor:
    """
    Extracts structured job application attributes from EmailMessage instances.
    Utilizes LLM AI agent analysis (Gemini/OpenAI) with intelligent regex parsing fallback.
    """

    @classmethod
    def extract_from_message(cls, email_msg) -> Optional[Dict[str, Any]]:
        subject = email_msg.subject or ''
        sender = f"{email_msg.sender_name} <{email_msg.sender_email}>" if email_msg.sender_name else email_msg.sender_email
        body = email_msg.body_text or email_msg.snippet or ''

        # 1. Attempt LLM AI Agent Classification & Attribute Extraction
        ai_res = AIJobClassifierService.analyze_email_with_llm(subject, sender, body)
        if ai_res is not None:
            email_msg.ai_reasoning = ai_res.get('reasoning', '')
            email_msg.extraction_source = 'AI_LLM'

            if not ai_res.get('is_job_related', False):
                return None

            return {
                'gmail_message_id': email_msg.gmail_message_id,
                'gmail_thread_id': email_msg.gmail_thread_id,
                'company_name': ai_res.get('company_name') or 'Unknown Company',
                'job_title': ai_res.get('job_title') or 'Software Engineer',
                'status': ai_res.get('status') or 'Applied',
                'applied_date': (email_msg.received_at.date() if email_msg.received_at else date.today()),
                'platform': ai_res.get('platform') or 'LinkedIn',
                'recruiter_name': ai_res.get('recruiter_name') or '',
                'recruiter_email': ai_res.get('recruiter_email') or email_msg.sender_email,
                'notes': f"AI Classified: {ai_res.get('reasoning', '')}",
                'source_email': email_msg.sender_email,
                'confidence': float(ai_res.get('confidence', 0.95)),
                'ai_reasoning': ai_res.get('reasoning', ''),
                'extraction_source': 'AI_LLM'
            }

        # 2. Hybrid Fallback: Rule-based regex parsing
        message_data = {
            'id': email_msg.gmail_message_id,
            'thread_id': email_msg.gmail_thread_id,
            'subject': subject,
            'from': sender,
            'date': email_msg.received_at.isoformat() if email_msg.received_at else '',
            'body': body
        }

        parsed = EmailJobParser.parse_email(message_data)
        if not parsed:
            email_msg.extraction_source = 'REGEX_PARSER'
            email_msg.ai_reasoning = 'Rule-based filter: Email does not contain job application keywords.'
            return None

        email_msg.extraction_source = 'REGEX_PARSER'
        email_msg.ai_reasoning = 'Rule-based regex parser extracted metadata based on email keywords and headers.'

        return {
            'gmail_message_id': email_msg.gmail_message_id,
            'gmail_thread_id': email_msg.gmail_thread_id,
            'company_name': parsed.get('company_name', 'Unknown Company'),
            'job_title': parsed.get('job_title', 'Software Engineer'),
            'status': parsed.get('status', 'Applied'),
            'applied_date': parsed.get('applied_date') or (email_msg.received_at.date() if email_msg.received_at else date.today()),
            'platform': parsed.get('platform', 'Other'),
            'recruiter_name': parsed.get('recruiter_name', ''),
            'recruiter_email': parsed.get('recruiter_email', email_msg.sender_email),
            'notes': parsed.get('notes', ''),
            'source_email': email_msg.sender_email,
            'confidence': 0.85,
            'ai_reasoning': 'Extracted via rule-based keyword matching.',
            'extraction_source': 'REGEX_PARSER'
        }
