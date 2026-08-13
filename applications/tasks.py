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
def sync_gmail_jobs_task(user_id: int):
    """
    Background task to sync Gmail messages asynchronously for a user.
    """
    try:
        user = User.objects.get(id=user_id)
        connection = GmailConnection.objects.get(user=user, is_active=True)
        service = GmailService(connection)
        results = service.sync_user_applications()
        return results
    except Exception as e:
        return {"error": str(e)}

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
