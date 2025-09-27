# chat/tasks.py
from celery import shared_task
from django.contrib.auth import get_user_model
from .models import Room, Message
import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from dc1.error_handling import enhanced_dual_write_manager, enhanced_dual_write, enhanced_read_with_fallback
from dc1.sync_manager import sync_manager

User = get_user_model()
logger = logging.getLogger("chat.tasks") # Configure in settings.py if needed


@shared_task
def process_chat_message(room_id, sender_username, message_content):
    """
    Celery task to save a chat message and broadcast it to the room group.
    Now uses dual database setup with MySQL primary and Neon secondary.
    """
    # Import necessary Django models and channel layer within the task
    # This is required because Celery tasks run in a separate environment

    User = get_user_model()
    # Use a different logger name for the worker process
    logger = logging.getLogger("chat.worker")

    try:
        # Get the room and sender user from the database with fallback
        @enhanced_read_with_fallback
        def get_room_and_sender():
            room = Room.objects.get(id=room_id)
            sender = User.objects.get(username=sender_username)
            return room, sender
        
        room, sender = get_room_and_sender()

        # Save the message to both databases using dual write
        @enhanced_dual_write
        def save_message():
            return Message.objects.create(room=room, sender=sender, content=message_content)
        
        message = save_message()
        logger.info("Message saved by worker to both databases: '%s' from '%s' in room '%s'.", 
                   message_content, sender_username, room.name)

        # Get the channel layer instance
        channel_layer = get_channel_layer()

        # Broadcast the message to the room group using the channel layer
        # Use async_to_sync to call the async group_send method from this sync task
        room_group_name = f"chat_{room.id}"
        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                "type": "chat_message", # This will call the chat_message method in consumers
                "message": message_content,
                "sender": sender_username,
                "sender_id": sender.id # Assuming sender has an 'id' attribute
            }
        )
        logger.info("Message broadcasted by worker to group %s", room_group_name)

    except Room.DoesNotExist:
        logger.error("Worker: Room with ID %s not found.", room_id)
    except User.DoesNotExist:
        logger.error("Worker: Sender user '%s' not found.", sender_username)
    except Exception as e:
        # Log the full traceback for better debugging in the worker logs
        logger.error("Worker error processing message: %s", e, exc_info=True)

@shared_task
def sync_data_to_neon(model_name, filters=None):
    """
    Celery task to synchronize data from MySQL to Neon
    """
    logger = logging.getLogger("chat.sync")
    
    try:
        # Import models dynamically
        from chat.models import Message, Room, UserProfile
        
        model_map = {
            'Message': Message,
            'Room': Room,
            'UserProfile': UserProfile,
        }
        
        model_class = model_map.get(model_name)
        if not model_class:
            logger.error(f"Unknown model: {model_name}")
            return
        
        # Perform sync
        result = sync_manager.full_sync(model_class, filters)
        logger.info(f"Sync task completed for {model_name}: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Sync task failed for {model_name}: {e}", exc_info=True)
        raise


@shared_task
def incremental_sync_data(model_name, last_sync_time=None):
    """
    Celery task for incremental data synchronization
    """
    logger = logging.getLogger("chat.sync")
    
    try:
        # Import models dynamically
        from chat.models import Message, Room, UserProfile
        
        model_map = {
            'Message': Message,
            'Room': Room,
            'UserProfile': UserProfile,
        }
        
        model_class = model_map.get(model_name)
        if not model_class:
            logger.error(f"Unknown model: {model_name}")
            return
        
        # Perform incremental sync
        result = sync_manager.incremental_sync(model_class, last_sync_time)
        logger.info(f"Incremental sync task completed for {model_name}: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Incremental sync task failed for {model_name}: {e}", exc_info=True)
        raise


@shared_task
def verify_data_consistency(model_name, sample_size=100):
    """
    Celery task to verify data consistency between MySQL and Neon
    """
    logger = logging.getLogger("chat.consistency")
    
    try:
        # Import models dynamically
        from chat.models import Message, Room, UserProfile
        
        model_map = {
            'Message': Message,
            'Room': Room,
            'UserProfile': UserProfile,
        }
        
        model_class = model_map.get(model_name)
        if not model_class:
            logger.error(f"Unknown model: {model_name}")
            return
        
        # Perform consistency check
        result = sync_manager.verify_consistency(model_class, sample_size)
        logger.info(f"Consistency check completed for {model_name}: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Consistency check failed for {model_name}: {e}", exc_info=True)
        raise


@shared_task
def repair_data_inconsistencies(model_name, inconsistencies):
    """
    Celery task to repair data inconsistencies
    """
    logger = logging.getLogger("chat.repair")
    
    try:
        # Import models dynamically
        from chat.models import Message, Room, UserProfile
        
        model_map = {
            'Message': Message,
            'Room': Room,
            'UserProfile': UserProfile,
        }
        
        model_class = model_map.get(model_name)
        if not model_class:
            logger.error(f"Unknown model: {model_name}")
            return
        
        # Perform repair
        result = sync_manager.repair_inconsistencies(model_class, inconsistencies)
        logger.info(f"Repair task completed for {model_name}: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Repair task failed for {model_name}: {e}", exc_info=True)
        raise

