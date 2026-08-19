import base64
import requests
import datetime
from email.utils import parseaddr
from typing import Dict, Any, List, Optional
from django.utils import timezone
from django.conf import settings
from applications.models import GmailConnection, Application, EmailMessage, EmailProcessingStatus
from applications.services.email_parser import EmailJobParser
from applications.services.job_extractor import JobExtractor
from applications.services.application_service import ApplicationService

GMAIL_API_BASE = "https://www.googleapis.com/gmail/v1/users/me"

class GmailService:
    def __init__(self, credential: GmailConnection):
        self.credential = credential

    @classmethod
    def get_auth_url(cls, redirect_uri: str, state: str = '') -> str:
        client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '')
        scope = "https://www.googleapis.com/auth/gmail.readonly"
        auth_url = (
            "https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={client_id}&"
            f"redirect_uri={redirect_uri}&"
            "response_type=code&"
            f"scope={scope}&"
            "access_type=offline&"
            "prompt=consent"
        )
        if state:
            auth_url += f"&state={state}"
        return auth_url

    def get_valid_access_token(self) -> str:
        if self.credential.refresh_token and self.credential.client_id and self.credential.client_secret:
            try:
                resp = requests.post(self.credential.token_uri, data={
                    'client_id': self.credential.client_id,
                    'client_secret': self.credential.client_secret,
                    'refresh_token': self.credential.refresh_token,
                    'grant_type': 'refresh_token',
                }, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    self.credential.access_token = data.get('access_token', self.credential.access_token)
                    self.credential.save()
            except Exception:
                pass
        return self.credential.access_token

    def fetch_job_emails(self, max_results: int = 20, query: str = None) -> List[Dict[str, Any]]:
        access_token = self.get_valid_access_token()
        headers = {'Authorization': f'Bearer {access_token}'}

        search_query = query or "application OR applied OR interview OR offer OR candidate OR recruiter OR role OR job OR greenhouse OR lever OR workday OR ashby OR careers OR hiring OR resume OR naukri OR indeed OR linkedin"
        list_url = f"{GMAIL_API_BASE}/messages"
        params = {
            'q': search_query,
            'maxResults': max_results
        }

        try:
            resp = requests.get(list_url, headers=headers, params=params, timeout=10)
            if resp.status_code != 200:
                print(f"Gmail API list messages error ({resp.status_code}): {resp.text}")
                return []
            
            message_list = resp.json().get('messages', [])

            # Fallback search if targeted search returns no messages
            if not message_list and not query:
                fb_params = {'maxResults': max_results}
                fb_resp = requests.get(list_url, headers=headers, params=fb_params, timeout=10)
                if fb_resp.status_code == 200:
                    message_list = fb_resp.json().get('messages', [])

            if not message_list:
                return []

            # Deduplicate against database before making HTTP requests for message details
            existing_ids = set(
                EmailMessage.objects.filter(
                    user=self.credential.user,
                    gmail_message_id__in=[item.get('id') for item in message_list if item.get('id')]
                ).values_list('gmail_message_id', flat=True)
            )

            new_items = [item for item in message_list if item.get('id') and item.get('id') not in existing_ids]

            fetched_emails = []

            # Parallelize detail fetching using ThreadPoolExecutor for fast execution (<2s)
            from concurrent.futures import ThreadPoolExecutor

            def fetch_single(item):
                msg_id = item.get('id')
                return self.get_message_detail(msg_id, headers)

            with ThreadPoolExecutor(max_workers=5) as executor:
                results = executor.map(fetch_single, new_items)
                for res in results:
                    if res:
                        fetched_emails.append(res)

            return fetched_emails
        except Exception as e:
            print(f"Error fetching Gmail messages: {str(e)}")
            return []

    def get_message_detail(self, message_id: str, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
        msg_url = f"{GMAIL_API_BASE}/messages/{message_id}?format=full"
        try:
            resp = requests.get(msg_url, headers=headers, timeout=10)
            if resp.status_code != 200:
                return None
            
            res_data = resp.json()
            payload = res_data.get('payload', {})
            headers_list = payload.get('headers', [])

            subject = ''
            sender = ''
            date_str = ''

            for h in headers_list:
                name = h.get('name', '').lower()
                if name == 'subject':
                    subject = h.get('value', '')
                elif name == 'from':
                    sender = h.get('value', '')
                elif name == 'date':
                    date_str = h.get('value', '')

            body = self.extract_body(payload)

            return {
                'id': message_id,
                'thread_id': res_data.get('threadId', ''),
                'subject': subject,
                'from': sender,
                'date': date_str,
                'body': body,
                'snippet': res_data.get('snippet', '')
            }
        except Exception:
            return None

    def extract_body(self, payload: Dict[str, Any]) -> str:
        body = ''
        if 'body' in payload and 'data' in payload['body']:
            try:
                body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
            except Exception:
                pass
        elif 'parts' in payload:
            for part in payload['parts']:
                mime_type = part.get('mimeType', '')
                if mime_type == 'text/plain' and 'data' in part.get('body', {}):
                    try:
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                        break
                    except Exception:
                        pass
                elif mime_type == 'text/html' and not body and 'data' in part.get('body', {}):
                    try:
                        raw_html = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                        body = self.clean_html(raw_html)
                    except Exception:
                        pass

        return body or payload.get('snippet', '')

    @staticmethod
    def clean_html(html: str) -> str:
        import re
        clean = re.sub(r'<[^<]+?>', ' ', html)
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()

    def sync_user_applications(self, emails_data: Optional[List[Dict[str, Any]]] = None, auto_approve: bool = False) -> Dict[str, Any]:
        """
        Stages raw email payload into EmailMessage table, executes job classification & extraction,
        populates extracted preview fields, and stages emails for manual user review.
        """
        self.credential.sync_status = 'IN_PROGRESS'
        self.credential.sync_started_at = timezone.now()
        self.credential.save()

        try:
            if emails_data is None:
                emails_data = self.fetch_job_emails()

            user = self.credential.user
            created_count = 0
            updated_count = 0
            skipped_count = 0
            pending_review_count = 0
            processed_emails = []

            for msg in emails_data:
                msg_id = msg.get('id', '')
                thread_id = msg.get('thread_id') or msg.get('threadId', '')
                sender_raw = msg.get('from', '')
                sender_name, sender_email = parseaddr(sender_raw)
                subject = msg.get('subject', '')
                body_text = msg.get('body', '')
                snippet = msg.get('snippet', '')
                raw_date = msg.get('date', '')
                parsed_date = EmailJobParser.parse_datetime(raw_date) if raw_date else timezone.now()

                # 1. Stage raw message in EmailMessage table
                email_msg, _ = EmailMessage.objects.get_or_create(
                    user=user,
                    gmail_message_id=msg_id,
                    defaults={
                        'gmail_thread_id': thread_id,
                        'sender_name': sender_name,
                        'sender_email': sender_email,
                        'subject': subject,
                        'received_at': parsed_date,
                        'body_text': body_text,
                        'snippet': snippet,
                        'processing_status': EmailProcessingStatus.PROCESSING
                    }
                )

                # 2. Extract structured job attributes
                extracted = JobExtractor.extract_from_message(email_msg)
                if not extracted:
                    email_msg.is_job_related = False
                    email_msg.processing_status = EmailProcessingStatus.IGNORED
                    email_msg.processed_at = timezone.now()
                    email_msg.save()
                    skipped_count += 1
                    continue

                email_msg.is_job_related = True
                email_msg.extracted_company_name = extracted.get('company_name', 'Unknown Company')
                email_msg.extracted_job_title = extracted.get('job_title', 'Software Engineer')
                email_msg.extracted_status = extracted.get('status', 'Applied')
                email_msg.extracted_platform = extracted.get('platform', 'Other')
                email_msg.extracted_recruiter_name = extracted.get('recruiter_name', '')
                email_msg.extracted_recruiter_email = extracted.get('recruiter_email', sender_email)
                email_msg.confidence_score = extracted.get('confidence', 0.95)
                email_msg.ai_reasoning = extracted.get('ai_reasoning', '')
                email_msg.extraction_source = extracted.get('extraction_source', 'REGEX_PARSER')

                if auto_approve:
                    # 3. Application deduplication and status mapping
                    app_record, is_created = ApplicationService.process_extracted_job_email(user, email_msg, extracted)

                    email_msg.processing_status = EmailProcessingStatus.PROCESSED
                    email_msg.processed_at = timezone.now()
                    email_msg.save()

                    if is_created:
                        created_count += 1
                    else:
                        updated_count += 1

                    processed_emails.append({
                        'id': msg_id,
                        'company_name': app_record.company_name,
                        'job_title': app_record.job_title,
                        'status': app_record.status,
                        'action': 'created' if is_created else 'updated'
                    })
                else:
                    email_msg.processing_status = EmailProcessingStatus.PENDING_REVIEW
                    email_msg.save()
                    pending_review_count += 1

                    processed_emails.append({
                        'id': msg_id,
                        'company_name': email_msg.extracted_company_name,
                        'job_title': email_msg.extracted_job_title,
                        'status': email_msg.extracted_status,
                        'action': 'pending_review'
                    })

            return {
                'scanned_emails_count': len(emails_data),
                'staged_emails_count': EmailMessage.objects.filter(user=user).count(),
                'created_count': created_count,
                'updated_count': updated_count,
                'pending_review_count': pending_review_count,
                'skipped_count': skipped_count,
                'processed_applications': processed_emails
            }
        finally:
            self.credential.sync_status = 'IDLE'
            self.credential.last_synced_at = timezone.now()
            self.credential.save()
