from functools import lru_cache

from supabase import Client, create_client

from src.app.core.config import get_config


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """
    Retorna una única instancia reutilizable del cliente de Supabase.

    El cache evita crear conexiones/clientes nuevos en cada rerun
    de Streamlit.
    """
    config = get_config()

    if not config.supabase.url:
        raise RuntimeError("SUPABASE_URL no está configurada.")

    if not config.supabase.key:
        raise RuntimeError("SUPABASE_KEY no está configurada.")

    return create_client(
        config.supabase.url,
        config.supabase.key,
    )


def clear_supabase_client_cache() -> None:
    """
    Limpia la instancia cacheada del cliente.

    Útil principalmente para tests o cuando se modifican
    dinámicamente las credenciales.
    """
    get_supabase_client.cache_clear()