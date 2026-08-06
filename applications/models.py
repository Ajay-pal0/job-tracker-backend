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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-applied_date', '-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'applied_date']),
        ]

    def __str__(self):
        return f"{self.company_name} - {self.job_title} ({self.status})"
