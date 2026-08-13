from django.utils import timezone
from typing import Dict, Any, Tuple
from ..models import Application, ApplicationEvent, EmailMessage, ApplicationStatus

class ApplicationService:
    """
    Business logic layer for deduplication, status transition, application updating,
    and event timeline logging.
    """

    @classmethod
    def process_extracted_job_email(
        cls,
        user,
        email_msg: EmailMessage,
        extracted_data: Dict[str, Any]
    ) -> Tuple[Application, bool]:
        company = extracted_data.get('company_name', 'Unknown Company')
        title = extracted_data.get('job_title', 'Role')
        status = extracted_data.get('status', ApplicationStatus.APPLIED)
        applied_date = extracted_data.get('applied_date') or timezone.now().date()
        platform = extracted_data.get('platform', 'Other')
        recruiter_name = extracted_data.get('recruiter_name', '')
        recruiter_email = extracted_data.get('recruiter_email', '')
        notes = extracted_data.get('notes', '')
        msg_id = extracted_data.get('gmail_message_id', '') or email_msg.gmail_message_id
        thread_id = extracted_data.get('gmail_thread_id', '')
        job_url = extracted_data.get('job_url', '')

        # Set default job_url to direct Gmail email link if not explicitly provided
        if not job_url and msg_id:
            job_url = f"https://mail.google.com/mail/u/0/#inbox/{msg_id}"

        # Multi-signal deduplication search
        existing = None
        if thread_id:
            existing = Application.objects.filter(user=user, gmail_thread_id=thread_id).first()
        if not existing and msg_id:
            existing = Application.objects.filter(user=user, gmail_message_id=msg_id).first()
        if not existing:
            existing = Application.objects.filter(
                user=user,
                company_name__iexact=company,
                job_title__iexact=title
            ).first()

        created = False
        now = timezone.now()

        if existing:
            # Update existing application status and fields if needed
            changed = False
            old_status = existing.status
            if existing.status != status and status != ApplicationStatus.APPLIED:
                existing.status = status
                changed = True
            
            if not existing.gmail_message_id and msg_id:
                existing.gmail_message_id = msg_id
                changed = True
            if not existing.gmail_thread_id and thread_id:
                existing.gmail_thread_id = thread_id
                changed = True
            if not existing.job_url and job_url:
                existing.job_url = job_url
                changed = True
            if recruiter_email and not existing.recruiter_email:
                existing.recruiter_email = recruiter_email
                changed = True

            existing.last_event_at = now
            existing.save()

            event_type = f"STATUS_UPDATE ({old_status} -> {existing.status})" if changed else "EMAIL_SYNC"
            description = f"Received email '{email_msg.subject}'. Status: {existing.status}"
            ApplicationEvent.objects.create(
                application=existing,
                email=email_msg,
                event_type=event_type,
                event_date=email_msg.received_at or now,
                description=description
            )
            app_record = existing
        else:
            # Create new application record
            app_record = Application.objects.create(
                user=user,
                company_name=company,
                job_title=title,
                applied_date=applied_date,
                status=status,
                platform=platform,
                job_url=job_url,
                recruiter_name=recruiter_name,
                recruiter_email=recruiter_email,
                notes=notes,
                gmail_message_id=msg_id,
                gmail_thread_id=thread_id,
                source_email=email_msg.sender_email,
                last_event_at=now
            )
            created = True

            ApplicationEvent.objects.create(
                application=app_record,
                email=email_msg,
                event_type="APPLICATION_CREATED",
                event_date=email_msg.received_at or now,
                description=f"Extracted from email subject: '{email_msg.subject}'"
            )

        return app_record, created
