import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def broadcast_user_event(user_id: int, event_type: str, payload: Dict[str, Any]) -> bool:
    """
    Modular, reusable WebSocket broadcast helper.
    Emits real-time JSON events to a specific user's channel group safely.
    Falls back gracefully if Django Channels or Redis channel layer is not active.

    :param user_id: ID of the recipient user
    :param event_type: Event identifier string (e.g. 'GMAIL_SYNC_STARTED', 'EMAIL_PROCESSED')
    :param payload: Event data dictionary
    :return: True if successfully dispatched to channel layer, False otherwise
    """
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        channel_layer = get_channel_layer()
        if channel_layer:
            group_name = f"user_{user_id}"
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    "type": "websocket_event",
                    "event": event_type,
                    "data": payload
                }
            )
            logger.info(f"WebSocket event '{event_type}' dispatched to group '{group_name}'.")
            return True
    except ImportError:
        logger.debug("Django Channels is not installed; WebSocket broadcast bypassed.")
    except Exception as e:
        logger.warning(f"Could not dispatch WebSocket event to user {user_id}: {e}")

    return False
