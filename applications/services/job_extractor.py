import re
from typing import Dict, Any, Optional
from datetime import date
from .email_parser import EmailJobParser

class JobExtractor:
    """
    Extracts structured job application attributes from EmailMessage instances.
    """

    @classmethod
    def extract_from_message(cls, email_msg) -> Optional[Dict[str, Any]]:
        message_data = {
            'id': email_msg.gmail_message_id,
            'thread_id': email_msg.gmail_thread_id,
            'subject': email_msg.subject,
            'from': f"{email_msg.sender_name} <{email_msg.sender_email}>" if email_msg.sender_name else email_msg.sender_email,
            'date': email_msg.received_at.isoformat() if email_msg.received_at else '',
            'body': email_msg.body_text or email_msg.snippet
        }

        parsed = EmailJobParser.parse_email(message_data)
        if not parsed:
            return None

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
            'confidence': 0.95
        }
