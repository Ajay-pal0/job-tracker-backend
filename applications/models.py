from django.db import models
from django.contrib.auth.models import User

class ApplicationStatus(models.TextChoices):
    WISHLIST = 'Wishlist', 'Wishlist'
    APPLIED = 'Applied', 'Applied'
    INTERVIEW_SCHEDULED = 'Interview Scheduled', 'Interview Scheduled'
    INTERVIEWING = 'Interviewing', 'Interviewing'
    OFFER = 'Offer', 'Offer'
    REJECTED = 'Rejected', 'Rejected'
    JOINED = 'Joined', 'Joined'
    WITHDRAWN = 'Withdrawn', 'Withdrawn'

class ApplicationPlatform(models.TextChoices):
    LINKEDIN = 'LinkedIn', 'LinkedIn'
    INDEED = 'Indeed', 'Indeed'
    NAUKRI = 'Naukri', 'Naukri'
    GLASSDOOR = 'Glassdoor', 'Glassdoor'
    COMPANY_WEBSITE = 'Company Website', 'Company Website'
    REFERRAL = 'Referral', 'Referral'
    OTHER = 'Other', 'Other'

class EmailProcessingStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    PENDING_REVIEW = 'PENDING_REVIEW', 'Pending Review'
    PROCESSING = 'PROCESSING', 'Processing'
    PROCESSED = 'PROCESSED', 'Processed'
    FAILED = 'FAILED', 'Failed'
    IGNORED = 'IGNORED', 'Ignored'

class Application(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applications')
    company_name = models.CharField(max_length=255)
    job_title = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True, default='')
    applied_date = models.DateField()
    status = models.CharField(
        max_length=50, 
        choices=ApplicationStatus.choices, 
        default=ApplicationStatus.APPLIED
    )
    salary = models.CharField(max_length=100, blank=True, default='')
    platform = models.CharField(
        max_length=100, 
        choices=ApplicationPlatform.choices, 
        default=ApplicationPlatform.LINKEDIN
    )
    job_url = models.URLField(max_length=500, blank=True, default='')
    recruiter_name = models.CharField(max_length=255, blank=True, default='')
    recruiter_email = models.EmailField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    gmail_message_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    gmail_thread_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    source_email = models.EmailField(blank=True, default='')
    last_event_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-applied_date', '-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'applied_date']),
            models.Index(fields=['user', 'gmail_message_id']),
            models.Index(fields=['user', 'gmail_thread_id']),
        ]

    def __str__(self):
        return f"{self.company_name} - {self.job_title} ({self.status})"


class GmailConnection(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='gmail_connection')
    email = models.EmailField(blank=True, default='')
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True, default='')
    token_uri = models.CharField(max_length=255, default='https://oauth2.googleapis.com/token')
    client_id = models.CharField(max_length=255, blank=True, default='')
    client_secret = models.CharField(max_length=255, blank=True, default='')
    scopes = models.TextField(blank=True, default='https://www.googleapis.com/auth/gmail.readonly')
    token_expiry = models.DateTimeField(null=True, blank=True)
    last_history_id = models.CharField(max_length=100, blank=True, default='')
    watch_expiration = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    sync_status = models.CharField(max_length=50, default='IDLE')
    sync_started_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def email_address(self):
        return self.email

    @email_address.setter
    def email_address(self, val):
        self.email = val

    def __str__(self):
        return f"GmailConnection ({self.user.username} - {self.email or 'Connected'})"


# Alias for backward compatibility
GmailCredential = GmailConnection


class EmailMessage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gmail_messages')
    gmail_message_id = models.CharField(max_length=255)
    gmail_thread_id = models.CharField(max_length=255, blank=True, default='')
    sender_name = models.CharField(max_length=255, blank=True, default='')
    sender_email = models.EmailField(blank=True, default='')
    subject = models.TextField(blank=True, default='')
    received_at = models.DateTimeField(null=True, blank=True)
    body_text = models.TextField(blank=True, default='')
    snippet = models.TextField(blank=True, default='')
    is_job_related = models.BooleanField(default=False)
    extracted_company_name = models.CharField(max_length=255, blank=True, default='')
    extracted_job_title = models.CharField(max_length=255, blank=True, default='')
    extracted_status = models.CharField(max_length=50, blank=True, default='Applied')
    extracted_platform = models.CharField(max_length=100, blank=True, default='LinkedIn')
    extracted_recruiter_name = models.CharField(max_length=255, blank=True, default='')
    extracted_recruiter_email = models.EmailField(blank=True, default='')
    confidence_score = models.FloatField(default=0.0)
    ai_reasoning = models.TextField(blank=True, default='')
    extraction_source = models.CharField(max_length=50, default='REGEX_PARSER')
    processing_status = models.CharField(
        max_length=50,
        choices=EmailProcessingStatus.choices,
        default=EmailProcessingStatus.PENDING
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-received_at', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'gmail_message_id'],
                name='unique_user_gmail_message'
            )
        ]
        indexes = [
            models.Index(fields=['user', 'received_at']),
            models.Index(fields=['user', 'processing_status']),
            models.Index(fields=['user', 'is_job_related']),
        ]

    def __str__(self):
        return f"EmailMessage ({self.user.username} - {self.subject[:30]})"


class ApplicationEvent(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='events')
    email = models.ForeignKey(EmailMessage, null=True, blank=True, on_delete=models.SET_NULL, related_name='application_events')
    event_type = models.CharField(max_length=100)
    event_date = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-event_date', '-created_at']

    def __str__(self):
        return f"ApplicationEvent ({self.application.company_name} - {self.event_type})"
