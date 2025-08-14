"""
Redis connection utilities for Heroku Key-Value Store and other Redis instances.

This module provides secure SSL configuration for Heroku Redis which uses
self-signed certificates requiring special handling.
"""

from urllib.parse import urlparse

from redis import Redis


def create_redis_connection(redis_url: str) -> Redis:
    """
    Create a Redis connection with proper SSL configuration for Heroku Key-Value Store.

    Heroku Key-Value Store uses self-signed certificates, which require disabling
    certificate verification while maintaining SSL encryption for security.

    Based on Heroku's official documentation:
    https://devcenter.heroku.com/articles/connecting-heroku-redis

    Args:
        redis_url: Redis connection URL (redis:// or rediss://)

    Returns:
        Redis connection object configured appropriately

    Example:
        >>> redis_conn = create_redis_connection(os.environ["REDIS_URL"])
        >>> redis_conn.ping()
        True
    """
    url = urlparse(redis_url)

    # Configure SSL for Heroku Redis (rediss://)
    if url.scheme == "rediss":
        return Redis(
            host=url.hostname,
            port=url.port,
            password=url.password,
            ssl=True,
            ssl_cert_reqs=None,  # Disable certificate verification for self-signed certs
            ssl_check_hostname=False,  # Disable hostname verification
        )
    else:
        # Regular Redis connection (redis://)
        return Redis.from_url(redis_url)
