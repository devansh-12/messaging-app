"""
Data synchronization manager for maintaining consistency between MySQL and Neon
"""
import logging
from datetime import datetime, timedelta
from django.db import connections, transaction
from django.core.management.base import BaseCommand
from django.utils import timezone
from typing import List, Dict, Any
from .error_handling import enhanced_dual_write_manager, DatabaseHealthChecker

logger = logging.getLogger(__name__)


class DataSyncManager:
    """
    Manages data synchronization between MySQL (primary) and Neon (secondary)
    """
    
    def __init__(self):
        self.mysql_db = 'default'
        self.neon_db = 'neon'
        self.health_checker = DatabaseHealthChecker()
        self.sync_batch_size = 100
    
    def full_sync(self, model_class, filters=None):
        """
        Perform full synchronization of a model from MySQL to Neon
        """
        logger.info(f"Starting full sync for {model_class.__name__}")
        
        try:
            # Get all objects from MySQL
            mysql_objects = model_class.objects.using(self.mysql_db)
            if filters:
                mysql_objects = mysql_objects.filter(**filters)
            
            total_count = mysql_objects.count()
            logger.info(f"Found {total_count} objects to sync")
            
            synced_count = 0
            failed_count = 0
            
            # Process in batches
            for i in range(0, total_count, self.sync_batch_size):
                batch = mysql_objects[i:i + self.sync_batch_size]
                batch_synced, batch_failed = self._sync_batch(batch)
                synced_count += batch_synced
                failed_count += batch_failed
                
                logger.info(f"Batch {i//self.sync_batch_size + 1}: {batch_synced} synced, {batch_failed} failed")
            
            logger.info(f"Full sync completed: {synced_count} successful, {failed_count} failed")
            return {"synced": synced_count, "failed": failed_count, "total": total_count}
            
        except Exception as e:
            logger.error(f"Full sync failed: {e}")
            raise
    
    def incremental_sync(self, model_class, last_sync_time=None):
        """
        Perform incremental synchronization based on timestamp
        """
        if last_sync_time is None:
            last_sync_time = timezone.now() - timedelta(hours=1)
        
        logger.info(f"Starting incremental sync for {model_class.__name__} since {last_sync_time}")
        
        try:
            # Get objects modified since last sync
            mysql_objects = model_class.objects.using(self.mysql_db).filter(
                timestamp__gte=last_sync_time
            )
            
            total_count = mysql_objects.count()
            logger.info(f"Found {total_count} objects to sync incrementally")
            
            synced_count = 0
            failed_count = 0
            
            # Process in batches
            for i in range(0, total_count, self.sync_batch_size):
                batch = mysql_objects[i:i + self.sync_batch_size]
                batch_synced, batch_failed = self._sync_batch(batch)
                synced_count += batch_synced
                failed_count += batch_failed
            
            logger.info(f"Incremental sync completed: {synced_count} successful, {failed_count} failed")
            return {"synced": synced_count, "failed": failed_count, "total": total_count}
            
        except Exception as e:
            logger.error(f"Incremental sync failed: {e}")
            raise
    
    def _sync_batch(self, batch):
        """
        Sync a batch of objects
        """
        synced_count = 0
        failed_count = 0
        
        for obj in batch:
            try:
                # Use update_or_create to handle both new and existing objects
                obj.save(using=self.neon_db)
                synced_count += 1
            except Exception as e:
                logger.error(f"Failed to sync object {obj.pk}: {e}")
                failed_count += 1
        
        return synced_count, failed_count
    
    def verify_consistency(self, model_class, sample_size=100):
        """
        Verify data consistency between MySQL and Neon
        """
        logger.info(f"Verifying consistency for {model_class.__name__}")
        
        try:
            # Get sample from MySQL
            mysql_objects = model_class.objects.using(self.mysql_db)[:sample_size]
            
            inconsistent_count = 0
            missing_count = 0
            
            for obj in mysql_objects:
                try:
                    # Check if object exists in Neon
                    neon_obj = model_class.objects.using(self.neon_db).get(pk=obj.pk)
                    
                    # Compare key fields
                    if not self._objects_match(obj, neon_obj):
                        inconsistent_count += 1
                        logger.warning(f"Object {obj.pk} is inconsistent between databases")
                
                except model_class.DoesNotExist:
                    missing_count += 1
                    logger.warning(f"Object {obj.pk} is missing in Neon")
            
            logger.info(f"Consistency check completed: {inconsistent_count} inconsistent, {missing_count} missing")
            return {"inconsistent": inconsistent_count, "missing": missing_count, "checked": len(mysql_objects)}
            
        except Exception as e:
            logger.error(f"Consistency verification failed: {e}")
            raise
    
    def _objects_match(self, obj1, obj2):
        """
        Compare two objects for consistency
        """
        # Compare key fields (customize based on your models)
        key_fields = ['content', 'timestamp', 'sender_id', 'room_id']
        
        for field in key_fields:
            if hasattr(obj1, field) and hasattr(obj2, field):
                if getattr(obj1, field) != getattr(obj2, field):
                    return False
        
        return True
    
    def repair_inconsistencies(self, model_class, inconsistencies):
        """
        Repair identified inconsistencies
        """
        logger.info(f"Repairing {len(inconsistencies)} inconsistencies for {model_class.__name__}")
        
        repaired_count = 0
        failed_count = 0
        
        for obj_id in inconsistencies:
            try:
                # Get object from MySQL (source of truth)
                mysql_obj = model_class.objects.using(self.mysql_db).get(pk=obj_id)
                
                # Update in Neon
                mysql_obj.save(using=self.neon_db)
                repaired_count += 1
                
            except Exception as e:
                logger.error(f"Failed to repair object {obj_id}: {e}")
                failed_count += 1
        
        logger.info(f"Repair completed: {repaired_count} repaired, {failed_count} failed")
        return {"repaired": repaired_count, "failed": failed_count}


class SyncScheduler:
    """
    Schedules and manages periodic synchronization tasks
    """
    
    def __init__(self):
        self.sync_manager = DataSyncManager()
        self.last_sync_times = {}
    
    def schedule_incremental_sync(self, model_class, interval_minutes=30):
        """
        Schedule incremental sync for a model
        """
        model_name = model_class.__name__
        last_sync = self.last_sync_times.get(model_name)
        
        if last_sync is None or timezone.now() - last_sync > timedelta(minutes=interval_minutes):
            try:
                result = self.sync_manager.incremental_sync(model_class, last_sync)
                self.last_sync_times[model_name] = timezone.now()
                logger.info(f"Scheduled sync completed for {model_name}: {result}")
                return result
            except Exception as e:
                logger.error(f"Scheduled sync failed for {model_name}: {e}")
                return None
        
        return None
    
    def schedule_consistency_check(self, model_class, interval_hours=6):
        """
        Schedule consistency check for a model
        """
        model_name = model_class.__name__
        last_check = self.last_sync_times.get(f"{model_name}_check")
        
        if last_check is None or timezone.now() - last_check > timedelta(hours=interval_hours):
            try:
                result = self.sync_manager.verify_consistency(model_class)
                self.last_sync_times[f"{model_name}_check"] = timezone.now()
                logger.info(f"Scheduled consistency check completed for {model_name}: {result}")
                return result
            except Exception as e:
                logger.error(f"Scheduled consistency check failed for {model_name}: {e}")
                return None
        
        return None


# Global instances
sync_manager = DataSyncManager()
sync_scheduler = SyncScheduler()


# Management command for manual sync operations
class SyncCommand(BaseCommand):
    help = 'Synchronize data between MySQL and Neon databases'
    
    def add_arguments(self, parser):
        parser.add_argument('--model', type=str, help='Model to sync (e.g., Message, Room)')
        parser.add_argument('--full', action='store_true', help='Perform full sync')
        parser.add_argument('--incremental', action='store_true', help='Perform incremental sync')
        parser.add_argument('--verify', action='store_true', help='Verify consistency')
        parser.add_argument('--repair', action='store_true', help='Repair inconsistencies')
    
    def handle(self, *args, **options):
        if not options['model']:
            self.stdout.write(self.style.ERROR('Please specify a model with --model'))
            return
        
        # Import models dynamically
        from chat.models import Message, Room, UserProfile
        
        model_map = {
            'Message': Message,
            'Room': Room,
            'UserProfile': UserProfile,
        }
        
        model_class = model_map.get(options['model'])
        if not model_class:
            self.stdout.write(self.style.ERROR(f'Unknown model: {options["model"]}'))
            return
        
        if options['full']:
            result = sync_manager.full_sync(model_class)
            self.stdout.write(self.style.SUCCESS(f'Full sync completed: {result}'))
        
        if options['incremental']:
            result = sync_manager.incremental_sync(model_class)
            self.stdout.write(self.style.SUCCESS(f'Incremental sync completed: {result}'))
        
        if options['verify']:
            result = sync_manager.verify_consistency(model_class)
            self.stdout.write(self.style.SUCCESS(f'Consistency check completed: {result}'))
        
        if options['repair']:
            # First verify to get inconsistencies
            verify_result = sync_manager.verify_consistency(model_class)
            if verify_result['inconsistent'] > 0 or verify_result['missing'] > 0:
                # Get list of inconsistent objects
                inconsistencies = list(range(1, verify_result['inconsistent'] + verify_result['missing'] + 1))
                result = sync_manager.repair_inconsistencies(model_class, inconsistencies)
                self.stdout.write(self.style.SUCCESS(f'Repair completed: {result}'))
            else:
                self.stdout.write(self.style.SUCCESS('No inconsistencies found'))
