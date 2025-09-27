# Dual Database Setup - MySQL Primary + Neon PostgreSQL Secondary

This implementation provides strong consistency with MySQL as the primary database and Neon PostgreSQL as the secondary database.

## Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Application   │    │   MySQL (Primary) │    │  Neon (Secondary) │
│                 │    │                 │    │                 │
│  ┌───────────┐  │    │  ┌───────────┐  │    │  ┌───────────┐  │
│  │   Reads   │──┼────┼──│   Reads   │  │    │  │   Reads   │  │
│  │ (Primary) │  │    │  │           │  │    │  │ (Fallback)│  │
│  └───────────┘  │    │  └───────────┘  │    │  └───────────┘  │
│                 │    │                 │    │                 │
│  ┌───────────┐  │    │  ┌───────────┐  │    │  ┌───────────┐  │
│  │  Writes   │──┼────┼──│  Writes   │  │    │  │  Writes   │  │
│  │ (Both DBs)│  │    │  │           │  │    │  │           │  │
│  └───────────┘  │    │  └───────────┘  │    │  └───────────┘  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Key Features

### 1. **Strong Consistency**
- All writes go to both databases simultaneously
- Reads prioritize MySQL, fallback to Neon on failure
- Automatic rollback if either database fails

### 2. **Error Handling & Retry Logic**
- Comprehensive error handling with retry mechanisms
- Database health checks before operations
- Graceful degradation when one database is unavailable

### 3. **Data Synchronization**
- Full sync capabilities for initial setup
- Incremental sync for ongoing consistency
- Consistency verification and repair tools

### 4. **Celery Integration**
- All database operations work seamlessly with Celery tasks
- Background sync and repair operations
- Asynchronous consistency checks

## Setup Instructions

### 1. Environment Variables

Add to your `.env` file:

```bash
# MySQL Configuration (Primary)
MYSQL_DATABASE=chatdb
MYSQL_USER=chatuser
MYSQL_PASSWORD=chatpass
MYSQL_HOST=db
MYSQL_PORT=3306

# Neon PostgreSQL Configuration (Secondary)
DATABASE_URL=postgresql://username:password@hostname/database?sslmode=require

# Alternative Neon Configuration (if not using DATABASE_URL)
NEON_USER=chatuser
NEON_PASSWORD=chatpass
NEON_HOST=your-neon-host
NEON_PORT=5432
```

### 2. Database Migrations

Run migrations on both databases:

```bash
# Migrate MySQL (primary)
python manage.py migrate --database=default

# Migrate Neon (secondary)
python manage.py migrate --database=neon
```

### 3. Initial Data Sync

```bash
# Full sync for all models
python manage.py dual_db_ops --model=Message --operation=sync --full
python manage.py dual_db_ops --model=Room --operation=sync --full
python manage.py dual_db_ops --model=UserProfile --operation=sync --full
```

## Usage Examples

### 1. **Basic Operations**

```python
from dc1.error_handling import enhanced_dual_write, enhanced_read_with_fallback

# Dual write operation
@enhanced_dual_write
def create_message(room, sender, content):
    return Message.objects.create(room=room, sender=sender, content=content)

# Read with fallback
@enhanced_read_with_fallback
def get_room_messages(room_id):
    return Message.objects.filter(room_id=room_id)
```

### 2. **Manual Database Operations**

```python
from dc1.error_handling import enhanced_dual_write_manager

# Direct dual write
def save_user_profile(user, bio):
    return enhanced_dual_write_manager.write_to_both(
        lambda: UserProfile.objects.create(user=user, bio=bio)
    )

# Read with fallback
def get_user_profile(user_id):
    return enhanced_dual_write_manager.read_with_fallback(
        lambda: UserProfile.objects.get(user_id=user_id)
    )
```

### 3. **Management Commands**

```bash
# Check database health
python manage.py dual_db_ops --operation=health

# Full sync
python manage.py dual_db_ops --model=Message --operation=sync --full

# Incremental sync
python manage.py dual_db_ops --model=Message --operation=sync --incremental

# Verify consistency
python manage.py dual_db_ops --model=Message --operation=verify

# Repair inconsistencies
python manage.py dual_db_ops --model=Message --operation=repair
```

### 4. **Celery Tasks**

```python
from chat.tasks import sync_data_to_neon, verify_data_consistency

# Schedule sync task
sync_data_to_neon.delay('Message')

# Schedule consistency check
verify_data_consistency.delay('Message', sample_size=1000)
```

## Monitoring & Maintenance

### 1. **Health Checks**

```bash
# Check database health
python manage.py dual_db_ops --operation=health
```

### 2. **Consistency Monitoring**

```bash
# Verify consistency for all models
python manage.py dual_db_ops --model=Message --operation=verify
python manage.py dual_db_ops --model=Room --operation=verify
python manage.py dual_db_ops --model=UserProfile --operation=verify
```

### 3. **Scheduled Tasks**

Set up periodic tasks in your Celery beat configuration:

```python
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'incremental-sync-messages': {
        'task': 'chat.tasks.incremental_sync_data',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
        'args': ('Message',)
    },
    'consistency-check': {
        'task': 'chat.tasks.verify_data_consistency',
        'schedule': crontab(hour='*/6'),  # Every 6 hours
        'args': ('Message', 1000)
    },
}
```

## Error Handling

### 1. **Retryable Errors**
- Connection timeouts
- Temporary network issues
- Database locks

### 2. **Non-Retryable Errors**
- Data integrity violations
- Authentication failures
- Schema mismatches

### 3. **Fallback Behavior**
- MySQL unavailable: Continue with Neon only
- Neon unavailable: Continue with MySQL only
- Both unavailable: Fail gracefully with error

## Performance Considerations

### 1. **Read Performance**
- MySQL is always tried first (lower latency)
- Neon fallback only on MySQL failure
- Caching can be added for frequently accessed data

### 2. **Write Performance**
- Dual writes add latency but ensure consistency
- Batch operations are supported
- Async operations via Celery for non-critical writes

### 3. **Sync Performance**
- Incremental syncs are much faster than full syncs
- Batch processing for large datasets
- Background processing via Celery

## Troubleshooting

### 1. **Connection Issues**

```bash
# Test MySQL connection
python manage.py dbshell --database=default

# Test Neon connection
python manage.py dbshell --database=neon
```

### 2. **Sync Issues**

```bash
# Check sync status
python manage.py dual_db_ops --model=Message --operation=verify

# Force full sync
python manage.py dual_db_ops --model=Message --operation=sync --full
```

### 3. **Consistency Issues**

```bash
# Verify consistency
python manage.py dual_db_ops --model=Message --operation=verify

# Repair inconsistencies
python manage.py dual_db_ops --model=Message --operation=repair
```

## Security Considerations

1. **Connection Strings**: Store sensitive connection strings in environment variables
2. **SSL**: Always use SSL for Neon connections
3. **Access Control**: Limit database access to necessary operations only
4. **Monitoring**: Monitor for unusual access patterns

## Backup & Recovery

1. **MySQL Backups**: Regular backups of primary database
2. **Neon Backups**: Neon provides automatic backups
3. **Cross-Database Recovery**: Use sync tools to restore consistency
4. **Point-in-Time Recovery**: Both databases support PITR

This setup provides strong consistency while maintaining high availability and performance for your chat application.
