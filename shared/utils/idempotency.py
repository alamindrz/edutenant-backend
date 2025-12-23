# shared/utils/idempotency.py
"""
Idempotency service to prevent duplicate processing.
Used for webhooks, payments, and other operations.
"""
from django.core.cache import cache


class IdempotencyService:
    """Service to ensure operations are processed only once."""
    
    @staticmethod
    def get_key(event_type, identifier):
        """Generate unique key for idempotency."""
        return f"idempotency_{event_type}_{identifier}"
    
    @staticmethod
    def check_and_lock(key, ttl=300):  # 5 minutes lock
        """
        Check if operation was already processed and lock for processing.
        Returns True if should proceed, False if duplicate.
        """
        # Try to set the lock
        if cache.add(f"{key}_lock", True, ttl):
            # Check if already processed
            if cache.get(f"{key}_processed"):
                # Release lock and return False (duplicate)
                cache.delete(f"{key}_lock")
                return False
            return True  # Proceed with processing
        return False  # Already being processed
    
    @staticmethod
    def mark_processed(key, ttl=24*60*60):  # 24 hours
        """Mark operation as successfully processed."""
        cache.set(f"{key}_processed", True, ttl)
        cache.delete(f"{key}_lock")  # Release lock
    
    @staticmethod
    def mark_failed(key):
        """Mark operation as failed (release lock for retry)."""
        cache.delete(f"{key}_lock")
    
    @staticmethod
    def clear_all():
        """Clear all idempotency locks (for testing/maintenance)."""
        # This is destructive - use with caution
        # In production, you would use a more targeted approach
        pass 