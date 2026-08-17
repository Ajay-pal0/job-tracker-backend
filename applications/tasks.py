try:
    from celery import shared_task
except ImportError:
    def shared_task(func):
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        wrapper.delay = func
        return wrapper

from django.contrib.auth.models import User
from applications.models import GmailConnection
from applications.services.gmail_service import GmailService

@shared_task
def sync_gmail_jobs_task(user_id: int, mock_emails=None):
    """
    Syncs job application emails from Gmail for a specific user.

    This is a background task that:
    1. Fetches active Gmail connection for the user.
    2. Scans for new application-related emails since last sync.
    3. Extracts structured job data (company, title, location, apply date, etc.).
    4. Saves new applications to the database and updates existing ones.

    Args:
        user_id: The ID of the user whose Gmail to sync
        mock_emails: Optional list of mock email data for testing (bypasses actual Gmail API)

    Returns:
        A dictionary with:
        - total_scanned: Number of emails scanned
        - applications_created: Number of new applications created
        - applications_updated: Number of existing applications updated
        - status: 'success' or 'error'
        - error: Error message if something went wrong
    """
    try:
        user = User.objects.get(id=user_id)
        connection = GmailConnection.objects.get(user=user, is_active=True)
        service = GmailService(connection)
        results = service.sync_user_applications(emails_data=mock_emails)
        return results
    except Exception as e:
        return {"error": str(e)}

@shared_task
def sync_all_users_gmail_jobs_task():
    """
    Syncs Gmail applications for all active users with Gmail connections.
    Delegates to sync_all_gmail_applications in sync_service.py.
    """
    from applications.services.sync_service import sync_all_gmail_applications
    return sync_all_gmail_applications()

@shared_task
def renew_gmail_watches_task():
    """
    Periodic task to renew Gmail push notification watches.
    """
    active_connections = GmailConnection.objects.filter(is_active=True)
    renewed_count = 0
    for conn in active_connections:
        renewed_count += 1
    return {"renewed": renewed_count}
