import re
import datetime
from email.utils import parseaddr, parsedate_to_datetime
from typing import Dict, Any, Optional
from django.utils import timezone
from applications.models import ApplicationStatus, ApplicationPlatform

GENERIC_DOMAINS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
    'greenhouse.io', 'lever.co', 'workday.com', 'ashbyhq.com',
    'smartrecruiters.com', 'jobvite.com', 'bamboohr.com',
    'linkedin.com', 'indeed.com', 'naukri.com', 'glassdoor.com'
}

ATS_PLATFORM_MAP = {
    'linkedin.com': ApplicationPlatform.LINKEDIN,
    'indeed.com': ApplicationPlatform.INDEED,
    'naukri.com': ApplicationPlatform.NAUKRI,
    'glassdoor.com': ApplicationPlatform.GLASSDOOR,
}

class EmailJobParser:
    """
    Parses raw Gmail email headers and body to extract job application metadata.
    """

    @classmethod
    def is_job_email(cls, subject: str, sender: str, body: str) -> bool:
        combined = f"{subject} {sender} {body}".lower()
        job_keywords = [
            'application', 'applied', 'interview', 'candidate', 'recruiter',
            'offer', 'position', 'opportunity', 'hiring', 'greenhouse',
            'lever', 'workday', 'ashby', 'smartrecruiters', 'jobvite',
            'naukri', 'indeed', 'linkedin', 'glassdoor', 'careers', 'talent',
            'resume', 'submission', 'schedule', 'screening', 'status', 'role',
            'thank you for', 'rejection', 'regret', 'job', 'applicant', 'hr'
        ]
        return any(kw in combined for kw in job_keywords)

    @classmethod
    def parse_email(cls, message_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parses a message dict containing 'id', 'subject', 'from', 'date', 'body'
        and returns structured job application dict or None if not job-related.
        """
        message_id = message_data.get('id', '')
        subject = message_data.get('subject', '').strip()
        sender_raw = message_data.get('from', '').strip()
        body = message_data.get('body', '').strip()
        raw_date = message_data.get('date', '')

        if not cls.is_job_email(subject, sender_raw, body):
            return None

        recruiter_name, recruiter_email = parseaddr(sender_raw)

        applied_date = cls.parse_date(raw_date)

        company_name = cls.extract_company_name(subject, recruiter_name, recruiter_email, body)
        job_title = cls.extract_job_title(subject, body)
        status = cls.classify_status(subject, body)
        platform = cls.detect_platform(recruiter_email, body)

        snippet = body[:300].replace('\n', ' ').strip()
        notes = f"Auto-extracted from Gmail (ID: {message_id}). Snippet: {snippet}"

        return {
            'gmail_message_id': message_id,
            'company_name': company_name or 'Unknown Company',
            'job_title': job_title or 'Job Applicant',
            'applied_date': applied_date,
            'status': status,
            'platform': platform,
            'recruiter_name': recruiter_name or '',
            'recruiter_email': recruiter_email or '',
            'notes': notes,
        }

    @classmethod
    def parse_datetime(cls, raw_date: str) -> datetime.datetime:
        if not raw_date:
            return timezone.now()
        try:
            dt = parsedate_to_datetime(raw_date)
            if timezone.is_naive(dt):
                return timezone.make_aware(dt, timezone.utc)
            return dt
        except Exception:
            return timezone.now()

    @classmethod
    def parse_date(cls, raw_date: str) -> datetime.date:
        return cls.parse_datetime(raw_date).date()

    @classmethod
    def extract_company_name(cls, subject: str, recruiter_name: str, recruiter_email: str, body: str) -> str:
        # 1. Direct patterns in subject
        subject_patterns = [
            r'Your application to\s+([A-Z0-9\s&\.\,-]+?)(?:\s+for|\s+position|\s+role|\s+at|\s*[\-\:\!\?]|\s*$)',
            r'Thank you for applying to\s+([A-Z0-9\s&\.\,-]+?)(?:\s+for|\s+position|\s+role|\s+at|\s*[\-\:\!\?]|\s*$)',
            r'Interview (?:invitation|with)?\s*(?:with)?\s+([A-Z0-9\s&\.\,-]+?)(?:\s+for|\s+position|\s+role|\s*[\-\:\!\?]|\s*$)',
            r'(?:application|applied)\s+(?:to|for)\s+([A-Z0-9\s&\.\,-]+?)(?:\s+for|\s+position|\s+role|\s+at|\s*[\-\:\!\?]|\s*$)',
            r'(?:at|with)\s+([A-Z0-9\s&\.\,-]+?)(?:\s+for|\s+-\s+|\s*$|[\!\.\?])',
            r'^([A-Z0-9\s&\.\,-]+?)\s*[\-\|:]\s*(?:Application|Interview|Job|Career)',
        ]

        for pat in subject_patterns:
            match = re.search(pat, subject, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                if len(candidate) > 1 and len(candidate) < 60 and not candidate.lower().startswith(('the ', 'a ')):
                    return candidate.title()

        # 2. Domain extraction from email address
        if recruiter_email and '@' in recruiter_email:
            domain = recruiter_email.split('@')[-1].lower()
            if domain not in GENERIC_DOMAINS:
                company_part = domain.split('.')[0]
                if len(company_part) > 2:
                    return company_part.capitalize()

        # 3. Check recruiter name (e.g., "Google Recruiting" or "Stripe Careers")
        if recruiter_name:
            clean_name = re.sub(r'(?i)(recruiting|careers|hr|team|talent|jobs|no-reply|notifications)', '', recruiter_name).strip()
            if clean_name and len(clean_name) > 1:
                return clean_name.title()

        return 'Company'


    @classmethod
    def extract_job_title(cls, subject: str, body: str) -> str:
        # Patterns in subject
        title_patterns = [
            r'(?:for|as)\s+(?:a|an)?\s*([A-Z][A-Za-z0-9\s\/\-\(\)]+?)(?:\s+role|\s+position|\s+at|\s+with|\s*[\-\|:]|\s*$)',
            r'Application for\s+([A-Z][A-Za-z0-9\s\/\-\(\)]+)',
            r'([A-Z][A-Za-z0-9\s\/\-\(\)]+?)\s+(?:Developer|Engineer|Manager|Analyst|Designer|Architect|Specialist|Lead|Consultant|Associate|Intern)',
        ]

        for pat in title_patterns:
            match = re.search(pat, subject, re.IGNORECASE)
            if match:
                title = match.group(0 if 'Developer' in pat else 1).strip()
                if len(title) > 2 and len(title) < 80:
                    return title.title()

        # Common job title fallback search in subject
        keywords = ['Engineer', 'Developer', 'Manager', 'Analyst', 'Designer', 'Architect', 'Specialist', 'Lead', 'Consultant', 'Data Scientist', 'Product Manager']
        for kw in keywords:
            if kw.lower() in subject.lower():
                return f"{kw} Role"

        return 'Software Engineer'

    @classmethod
    def classify_status(cls, subject: str, body: str) -> str:
        combined = f"{subject} {body}".lower()

        # Rejection patterns
        rejection_phrases = [
            'not moving forward', 'regret to inform', 'selected another candidate',
            'decided to proceed with other', 'unfortunate news', 'position has been filled',
            'will not be moving forward', 'pursuing other candidates', 'decline'
        ]
        if any(phrase in combined for phrase in rejection_phrases):
            return ApplicationStatus.REJECTED

        # Offer patterns
        offer_phrases = [
            'pleased to offer', 'offer of employment', 'congratulations on your offer',
            'extending an offer', 'job offer'
        ]
        if any(phrase in combined for phrase in offer_phrases):
            return ApplicationStatus.OFFER

        # Interview patterns
        interview_phrases = [
            'schedule an interview', 'interview invitation', 'screening call',
            'technical interview', 'invited to interview', 'next round',
            'interview confirmation', 'schedule a call'
        ]
        if any(phrase in combined for phrase in interview_phrases):
            return ApplicationStatus.INTERVIEW_SCHEDULED

        return ApplicationStatus.APPLIED

    @classmethod
    def detect_platform(cls, recruiter_email: str, body: str) -> str:
        domain = recruiter_email.split('@')[-1].lower() if '@' in recruiter_email else ''
        for key, platform in ATS_PLATFORM_MAP.items():
            if key in domain or key in body.lower():
                return platform
        return ApplicationPlatform.COMPANY_WEBSITE
