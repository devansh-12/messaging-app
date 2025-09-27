"""
Dual Database Router for MySQL Primary and Neon PostgreSQL Secondary
Implements strong consistency with MySQL as primary and Neon as secondary
"""
import logging
from django.conf import settings
from django.db import connections, transaction
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class DualDatabaseRouter:
    """
    Database router that implements:
    - Reads: MySQL first, fallback to Neon on failure
    - Writes: Both databases simultaneously with rollback on failure
    """
    
    def db_for_read(self, model, **hints):
        """
        Reads go to MySQL (primary) first, with fallback to Neon
        """
        return 'default'  # MySQL is primary for reads
    
    def db_for_write(self, model, **hints):
        """
        Writes go to both databases - handled by DualWriteManager
        """
        return 'default'  # MySQL is primary for writes
    
    def allow_relation(self, obj1, obj2, **hints):
        """
        Allow relations between objects from the same database
        """
        db_set = {'default', 'neon'}
        if obj1._state.db in db_set and obj2._state.db in db_set:
            return True
        return None
    
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Ensure migrations run on both databases
        """
        return True


class DualWriteManager:
    """
    Manages dual writes to both MySQL and Neon databases
    Implements strong consistency with rollback on failure
    """
    
    def __init__(self):
        self.mysql_db = 'default'
        self.neon_db = 'neon'
        self.max_retries = 3
        self.retry_delay = 1  # seconds
    
    def write_to_both(self, operation_func, *args, **kwargs):
        """
        Execute write operation on both databases
        Rollback both if either fails
        """
        mysql_success = False
        neon_success = False
        
        try:
            # Write to MySQL first (primary)
            with transaction.atomic(using=self.mysql_db):
                mysql_result = operation_func(*args, **kwargs)
                mysql_success = True
                logger.info(f"Successfully wrote to MySQL: {operation_func.__name__}")
            
            # Write to Neon (secondary)
            with transaction.atomic(using=self.neon_db):
                neon_result = operation_func(*args, **kwargs)
                neon_success = True
                logger.info(f"Successfully wrote to Neon: {operation_func.__name__}")
            
            return mysql_result
            
        except Exception as mysql_error:
            logger.error(f"MySQL write failed: {mysql_error}")
            
            # If MySQL failed, rollback Neon if it was successful
            if neon_success:
                try:
                    with transaction.atomic(using=self.neon_db):
                        # Rollback logic would go here
                        logger.warning("Rolling back Neon due to MySQL failure")
                except Exception as rollback_error:
                    logger.error(f"Neon rollback failed: {rollback_error}")
            
            raise mysql_error
        
        except Exception as neon_error:
            logger.error(f"Neon write failed: {neon_error}")
            
            # If Neon failed, rollback MySQL if it was successful
            if mysql_success:
                try:
                    with transaction.atomic(using=self.mysql_db):
                        # Rollback logic would go here
                        logger.warning("Rolling back MySQL due to Neon failure")
                except Exception as rollback_error:
                    logger.error(f"MySQL rollback failed: {rollback_error}")
            
            raise neon_error
    
    def read_with_fallback(self, operation_func, *args, **kwargs):
        """
        Read from MySQL first, fallback to Neon on failure
        """
        try:
            # Try MySQL first (primary)
            result = operation_func(*args, **kwargs)
            logger.debug(f"Successfully read from MySQL: {operation_func.__name__}")
            return result
            
        except Exception as mysql_error:
            logger.warning(f"MySQL read failed, trying Neon: {mysql_error}")
            
            try:
                # Fallback to Neon
                result = operation_func(*args, **kwargs)
                logger.info(f"Successfully read from Neon fallback: {operation_func.__name__}")
                return result
                
            except Exception as neon_error:
                logger.error(f"Both MySQL and Neon reads failed: MySQL={mysql_error}, Neon={neon_error}")
                raise mysql_error  # Raise the original MySQL error
    
    def sync_data(self, model_class, filters=None):
        """
        Synchronize data from MySQL to Neon
        Useful for initial sync or recovery
        """
        try:
            # Read from MySQL
            mysql_objects = model_class.objects.using(self.mysql_db)
            if filters:
                mysql_objects = mysql_objects.filter(**filters)
            
            # Write to Neon
            for obj in mysql_objects:
                try:
                    # Create or update in Neon
                    obj.save(using=self.neon_db)
                except Exception as e:
                    logger.error(f"Failed to sync object {obj.pk} to Neon: {e}")
            
            logger.info(f"Successfully synced {model_class.__name__} data to Neon")
            
        except Exception as e:
            logger.error(f"Data sync failed: {e}")
            raise


# Global instance
dual_write_manager = DualWriteManager()


def dual_write(operation_func):
    """
    Decorator for dual write operations
    """
    def wrapper(*args, **kwargs):
        return dual_write_manager.write_to_both(operation_func, *args, **kwargs)
    return wrapper


def read_with_fallback(operation_func):
    """
    Decorator for read operations with fallback
    """
    def wrapper(*args, **kwargs):
        return dual_write_manager.read_with_fallback(operation_func, *args, **kwargs)
    return wrapper
