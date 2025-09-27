"""
Error handling and retry mechanisms for dual database operations
"""
import time
import logging
from functools import wraps
from django.db import connections, transaction, IntegrityError, OperationalError
from django.core.exceptions import ImproperlyConfigured
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom exception for database operations"""
    pass


class RetryableError(DatabaseError):
    """Error that can be retried"""
    pass


class NonRetryableError(DatabaseError):
    """Error that should not be retried"""
    pass


def retry_on_failure(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Decorator for retrying operations on failure
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except RetryableError as e:
                    last_exception = e
                    if attempt < max_retries:
                        wait_time = delay * (backoff ** attempt)
                        logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"All {max_retries + 1} attempts failed for {func.__name__}")
                        raise e
                except NonRetryableError as e:
                    logger.error(f"Non-retryable error in {func.__name__}: {e}")
                    raise e
                except Exception as e:
                    # Convert unexpected exceptions to retryable errors
                    last_exception = RetryableError(f"Unexpected error: {e}")
                    if attempt < max_retries:
                        wait_time = delay * (backoff ** attempt)
                        logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"All {max_retries + 1} attempts failed for {func.__name__}")
                        raise last_exception
            
            raise last_exception
        return wrapper
    return decorator


class DatabaseHealthChecker:
    """
    Check database health and connectivity
    """
    
    def __init__(self):
        self.mysql_db = 'default'
        self.neon_db = 'neon'
    
    def check_database_health(self, db_alias: str) -> bool:
        """
        Check if a database is healthy and accessible
        """
        try:
            connection = connections[db_alias]
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                return result[0] == 1
        except Exception as e:
            logger.error(f"Database {db_alias} health check failed: {e}")
            return False
    
    def get_healthy_databases(self) -> list:
        """
        Get list of healthy databases
        """
        healthy_dbs = []
        
        if self.check_database_health(self.mysql_db):
            healthy_dbs.append(self.mysql_db)
        
        if self.check_database_health(self.neon_db):
            healthy_dbs.append(self.neon_db)
        
        return healthy_dbs
    
    def is_mysql_healthy(self) -> bool:
        """Check if MySQL is healthy"""
        return self.check_database_health(self.mysql_db)
    
    def is_neon_healthy(self) -> bool:
        """Check if Neon is healthy"""
        return self.check_database_health(self.neon_db)


class EnhancedDualWriteManager:
    """
    Enhanced dual write manager with comprehensive error handling
    """
    
    def __init__(self):
        self.mysql_db = 'default'
        self.neon_db = 'neon'
        self.health_checker = DatabaseHealthChecker()
        self.max_retries = 3
        self.retry_delay = 1.0
    
    @retry_on_failure(max_retries=3, delay=1.0)
    def write_to_both(self, operation_func: Callable, *args, **kwargs):
        """
        Execute write operation on both databases with enhanced error handling
        """
        mysql_success = False
        neon_success = False
        mysql_result = None
        neon_result = None
        
        # Check database health before operations
        if not self.health_checker.is_mysql_healthy():
            raise NonRetryableError("MySQL database is not healthy")
        
        if not self.health_checker.is_neon_healthy():
            logger.warning("Neon database is not healthy, proceeding with MySQL only")
            # Continue with MySQL only if Neon is down
        
        try:
            # Write to MySQL first (primary)
            with transaction.atomic(using=self.mysql_db):
                mysql_result = operation_func(*args, **kwargs)
                mysql_success = True
                logger.info(f"Successfully wrote to MySQL: {operation_func.__name__}")
            
            # Write to Neon (secondary) if healthy
            if self.health_checker.is_neon_healthy():
                with transaction.atomic(using=self.neon_db):
                    neon_result = operation_func(*args, **kwargs)
                    neon_success = True
                    logger.info(f"Successfully wrote to Neon: {operation_func.__name__}")
            else:
                logger.warning("Skipping Neon write due to health check failure")
                neon_success = True  # Consider it successful if we skip due to health
            
            return mysql_result
            
        except IntegrityError as e:
            logger.error(f"Integrity error during write: {e}")
            raise NonRetryableError(f"Data integrity violation: {e}")
        
        except OperationalError as e:
            logger.error(f"Operational error during write: {e}")
            raise RetryableError(f"Database operation failed: {e}")
        
        except Exception as e:
            logger.error(f"Unexpected error during write: {e}")
            raise RetryableError(f"Unexpected error: {e}")
    
    @retry_on_failure(max_retries=3, delay=1.0)
    def read_with_fallback(self, operation_func: Callable, *args, **kwargs):
        """
        Read from MySQL first, fallback to Neon on failure
        """
        # Check database health
        if not self.health_checker.is_mysql_healthy() and not self.health_checker.is_neon_healthy():
            raise NonRetryableError("Both databases are unhealthy")
        
        try:
            # Try MySQL first (primary)
            if self.health_checker.is_mysql_healthy():
                result = operation_func(*args, **kwargs)
                logger.debug(f"Successfully read from MySQL: {operation_func.__name__}")
                return result
            else:
                logger.warning("MySQL is unhealthy, trying Neon directly")
                raise RetryableError("MySQL is unhealthy")
            
        except Exception as mysql_error:
            logger.warning(f"MySQL read failed, trying Neon: {mysql_error}")
            
            if not self.health_checker.is_neon_healthy():
                raise NonRetryableError("Both MySQL and Neon are unhealthy")
            
            try:
                # Fallback to Neon
                result = operation_func(*args, **kwargs)
                logger.info(f"Successfully read from Neon fallback: {operation_func.__name__}")
                return result
                
            except Exception as neon_error:
                logger.error(f"Both MySQL and Neon reads failed: MySQL={mysql_error}, Neon={neon_error}")
                raise RetryableError(f"Both databases failed: MySQL={mysql_error}, Neon={neon_error}")
    
    def sync_data_with_retry(self, model_class, filters=None):
        """
        Synchronize data from MySQL to Neon with retry logic
        """
        @retry_on_failure(max_retries=3, delay=2.0)
        def _sync_operation():
            return self._sync_data_internal(model_class, filters)
        
        return _sync_operation()
    
    def _sync_data_internal(self, model_class, filters=None):
        """
        Internal sync operation
        """
        try:
            # Read from MySQL
            mysql_objects = model_class.objects.using(self.mysql_db)
            if filters:
                mysql_objects = mysql_objects.filter(**filters)
            
            synced_count = 0
            failed_count = 0
            
            # Write to Neon
            for obj in mysql_objects:
                try:
                    # Create or update in Neon
                    obj.save(using=self.neon_db)
                    synced_count += 1
                except Exception as e:
                    logger.error(f"Failed to sync object {obj.pk} to Neon: {e}")
                    failed_count += 1
            
            logger.info(f"Sync completed: {synced_count} successful, {failed_count} failed for {model_class.__name__}")
            return {"synced": synced_count, "failed": failed_count}
            
        except Exception as e:
            logger.error(f"Data sync failed: {e}")
            raise RetryableError(f"Sync operation failed: {e}")


# Global enhanced instance
enhanced_dual_write_manager = EnhancedDualWriteManager()


def enhanced_dual_write(operation_func):
    """
    Enhanced decorator for dual write operations
    """
    def wrapper(*args, **kwargs):
        return enhanced_dual_write_manager.write_to_both(operation_func, *args, **kwargs)
    return wrapper


def enhanced_read_with_fallback(operation_func):
    """
    Enhanced decorator for read operations with fallback
    """
    def wrapper(*args, **kwargs):
        return enhanced_dual_write_manager.read_with_fallback(operation_func, *args, **kwargs)
    return wrapper
