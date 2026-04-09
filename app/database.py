from functools import lru_cache

from supabase import create_client, Client

from app.config import get_settings


@lru_cache()
def get_supabase_client() -> Client:
    """Return a cached Supabase client using the service_role key (full access).

    The client is created once and reused across all requests to avoid
    creating expensive new HTTP sessions on every call.
    """
    settings = get_settings()
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


@lru_cache()
def get_supabase_auth_client() -> Client:
    """Return a cached Supabase client using the anon key (user-facing auth).

    The client is created once and reused across all requests.
    """
    settings = get_settings()
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
