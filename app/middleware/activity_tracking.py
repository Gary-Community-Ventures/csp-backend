"""
Middleware to track user activity by hour.

This middleware records when providers and families are active on the site,
creating one record per user per hour in the UserActivity table.

Uses Redis caching to avoid hitting the database on every request.
"""

from datetime import datetime, timezone

import sentry_sdk
from flask import current_app, g

from app.auth.helpers import get_current_user
from app.extensions import db
from app.models import UserActivity

# Cache activity records for 2 hours (in seconds)
ACTIVITY_CACHE_TTL = 2 * 60 * 60


def _get_redis_cache_key(user_type: str, user_id: str, hour_timestamp: datetime) -> str:
    """Generate Redis cache key for activity tracking."""
    hour_str = hour_timestamp.strftime("%Y-%m-%d-%H")
    return f"user_activity:{user_type}:{user_id}:{hour_str}"


def _is_activity_cached(redis_conn, cache_key: str) -> bool:
    """Check if activity has already been recorded this hour."""
    return redis_conn.exists(cache_key) > 0


def _cache_activity(redis_conn, cache_key: str):
    """Cache that activity was recorded for this hour."""
    redis_conn.setex(cache_key, ACTIVITY_CACHE_TTL, "1")  # 2 hour TTL


def track_user_activity():
    """
    Track user activity for the current request.

    Should be called after request processing (in an after_request handler)
    to avoid impacting request performance if there are DB issues.

    Uses Redis to cache already-tracked hours and avoid unnecessary DB queries.
    """
    try:
        user = get_current_user()

        if user is None:
            # Not authenticated, nothing to track
            return

        # Check if we've already tracked this user this hour (to avoid duplicate DB calls)
        # Store in g to persist for this request only
        if hasattr(g, "_activity_tracked") and g._activity_tracked:
            return

        now = datetime.now(timezone.utc)
        hour = UserActivity.truncate_to_hour(now)

        # Get Redis connection from job manager
        from app.jobs import job_manager

        redis_conn = job_manager.get_redis()

        if not redis_conn:
            current_app.logger.warning("Redis not available, skipping activity cache check")
            # Fall back to non-cached behavior
            _track_without_cache(user, now)
            return

        # Check Redis cache and record activity if needed
        records_to_cache = []

        if user.user_data.provider_id:
            cache_key = _get_redis_cache_key("provider", user.user_data.provider_id, hour)
            if not _is_activity_cached(redis_conn, cache_key):
                activity = UserActivity.record_provider_activity(user.user_data.provider_id, now)
                if activity is not None:
                    db.session.add(activity)
                records_to_cache.append(cache_key)

        if user.user_data.family_id:
            cache_key = _get_redis_cache_key("family", user.user_data.family_id, hour)
            if not _is_activity_cached(redis_conn, cache_key):
                activity = UserActivity.record_family_activity(user.user_data.family_id, now)
                if activity is not None:
                    db.session.add(activity)
                records_to_cache.append(cache_key)

        # Single commit for all records
        if records_to_cache:
            db.session.commit()
            for cache_key in records_to_cache:
                _cache_activity(redis_conn, cache_key)

        # Mark as tracked for this request
        g._activity_tracked = True

    except Exception as e:
        # Log error but don't break the request
        current_app.logger.error(f"Error tracking user activity: {e}")
        # Send to Sentry
        sentry_sdk.capture_exception(e)
        # Rollback any partial changes
        db.session.rollback()


def _track_without_cache(user, now: datetime):
    """Fallback to track activity without Redis cache."""
    if user.user_data.provider_id:
        activity = UserActivity.record_provider_activity(user.user_data.provider_id, now)
        if activity is not None:
            db.session.add(activity)

    if user.user_data.family_id:
        activity = UserActivity.record_family_activity(user.user_data.family_id, now)
        if activity is not None:
            db.session.add(activity)

    db.session.commit()
