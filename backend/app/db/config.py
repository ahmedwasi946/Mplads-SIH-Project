from app.core.config import settings


def get_database_url() -> str:
    """Return the configured PostgreSQL URL."""
    return settings.database_url