import logging
from django.core.cache import cache
from applications.models import GmailConnection
from applications.services.gmail_service import GmailService

logger = logging.getLogger(__name__)
LOCK_EXPIRE = 60 * 10  # 10 minutes lock timeout

def sync_all_gmail_applications(mock_emails=None) -> dict:
    """
    Synchronizes Gmail job applications across all active user connections.
    Uses Django cache lock to prevent concurrent overlapping sync executions.
    """
    # Prevent overlapping sync runs
    lock_acquired = cache.add('gmail_sync_lock', 'locked', LOCK_EXPIRE)
    if not lock_acquired:
        logger.info("Gmail sync is already in progress. Skipping execution.")
        return {
            'status': 'skipped',
            'reason': 'Sync execution already in progress (lock acquired).'
        }

    try:
        active_connections = GmailConnection.objects.filter(is_active=True)
        total_connections = active_connections.count()
        synced_count = 0
        failed_count = 0
        results = []

        logger.info(f"Starting batch Gmail sync for {total_connections} active user connections.")

        for connection in active_connections:
            user_info = f"User ID {connection.user_id} ({connection.email or connection.user.email})"
            try:
                service = GmailService(connection)
                sync_res = service.sync_user_applications(emails_data=mock_emails)
                synced_count += 1
                results.append({
                    'user_id': connection.user_id,
                    'status': 'success',
                    'scanned': sync_res.get('scanned_emails_count', 0),
                    'pending_review': sync_res.get('pending_review_count', 0)
                })
                logger.info(f"Successfully synced Gmail for {user_info}.")
            except Exception as e:
                failed_count += 1
                logger.error(f"Failed to sync Gmail for {user_info}: {str(e)}")
                results.append({
                    'user_id': connection.user_id,
                    'status': 'failed',
                    'error': str(e)
                })

        return {
            'status': 'completed',
            'total_users': total_connections,
            'synced_users': synced_count,
            'failed_users': failed_count,
            'user_results': results
        }

    finally:
        # Release distributed lock
        cache.delete('gmail_sync_lock')
