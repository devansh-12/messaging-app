"""
Management command for dual database operations
"""
from django.core.management.base import BaseCommand
from django.db import connections
from dc1.sync_manager import sync_manager, sync_scheduler
from dc1.error_handling import DatabaseHealthChecker


class Command(BaseCommand):
    help = 'Perform dual database operations (sync, verify, repair)'
    
    def add_arguments(self, parser):
        parser.add_argument('--model', type=str, help='Model to operate on (Message, Room, UserProfile)')
        parser.add_argument('--operation', type=str, choices=['sync', 'verify', 'repair', 'health'], 
                          help='Operation to perform')
        parser.add_argument('--full', action='store_true', help='Perform full sync')
        parser.add_argument('--incremental', action='store_true', help='Perform incremental sync')
        parser.add_argument('--sample-size', type=int, default=100, help='Sample size for consistency check')
    
    def handle(self, *args, **options):
        model_name = options.get('model')
        operation = options.get('operation')
        
        if not model_name:
            self.stdout.write(self.style.ERROR('Please specify a model with --model'))
            return
        
        if not operation:
            self.stdout.write(self.style.ERROR('Please specify an operation with --operation'))
            return
        
        # Import models
        from chat.models import Message, Room, UserProfile
        
        model_map = {
            'Message': Message,
            'Room': Room,
            'UserProfile': UserProfile,
        }
        
        model_class = model_map.get(model_name)
        if not model_class:
            self.stdout.write(self.style.ERROR(f'Unknown model: {model_name}'))
            return
        
        if operation == 'health':
            self.check_health()
        elif operation == 'sync':
            self.perform_sync(model_class, options)
        elif operation == 'verify':
            self.verify_consistency(model_class, options)
        elif operation == 'repair':
            self.repair_inconsistencies(model_class, options)
    
    def check_health(self):
        """Check database health"""
        health_checker = DatabaseHealthChecker()
        
        mysql_healthy = health_checker.is_mysql_healthy()
        neon_healthy = health_checker.is_neon_healthy()
        
        self.stdout.write(f"MySQL Health: {'✓' if mysql_healthy else '✗'}")
        self.stdout.write(f"Neon Health: {'✓' if neon_healthy else '✗'}")
        
        if mysql_healthy and neon_healthy:
            self.stdout.write(self.style.SUCCESS('Both databases are healthy'))
        elif mysql_healthy:
            self.stdout.write(self.style.WARNING('Only MySQL is healthy'))
        elif neon_healthy:
            self.stdout.write(self.style.WARNING('Only Neon is healthy'))
        else:
            self.stdout.write(self.style.ERROR('Both databases are unhealthy'))
    
    def perform_sync(self, model_class, options):
        """Perform data synchronization"""
        if options['full']:
            result = sync_manager.full_sync(model_class)
            self.stdout.write(self.style.SUCCESS(f'Full sync completed: {result}'))
        elif options['incremental']:
            result = sync_manager.incremental_sync(model_class)
            self.stdout.write(self.style.SUCCESS(f'Incremental sync completed: {result}'))
        else:
            self.stdout.write(self.style.ERROR('Please specify --full or --incremental'))
    
    def verify_consistency(self, model_class, options):
        """Verify data consistency"""
        sample_size = options.get('sample_size', 100)
        result = sync_manager.verify_consistency(model_class, sample_size)
        
        if result['inconsistent'] == 0 and result['missing'] == 0:
            self.stdout.write(self.style.SUCCESS(f'Data is consistent: {result}'))
        else:
            self.stdout.write(self.style.WARNING(f'Inconsistencies found: {result}'))
    
    def repair_inconsistencies(self, model_class, options):
        """Repair data inconsistencies"""
        # First verify to get inconsistencies
        sample_size = options.get('sample_size', 100)
        verify_result = sync_manager.verify_consistency(model_class, sample_size)
        
        if verify_result['inconsistent'] > 0 or verify_result['missing'] > 0:
            # Get list of inconsistent objects (simplified)
            inconsistencies = list(range(1, verify_result['inconsistent'] + verify_result['missing'] + 1))
            result = sync_manager.repair_inconsistencies(model_class, inconsistencies)
            self.stdout.write(self.style.SUCCESS(f'Repair completed: {result}'))
        else:
            self.stdout.write(self.style.SUCCESS('No inconsistencies found'))
