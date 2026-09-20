from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    key: str


@dataclass(frozen=True)
class AppConfig:
    app_name: str
    environment: str
    supabase: SupabaseConfig
    # Cuando está en False la app no pide login. Solo para uso local:
    # al publicarla hay que volver a activarlo.
    auth_enabled: bool = True
    # Carpeta con el Superhomologador, la Circular 022 y Máximos y Mínimos.
    referencias_path: str = "referencias"


def _como_booleano(valor) -> bool:
    """Interpreta el valor del secrets, venga como texto o como booleano."""

    if isinstance(valor, bool):
        return valor

    return str(valor).strip().lower() not in {"false", "0", "no", ""}


def get_config() -> AppConfig:
    """Carga la configuración de la aplicación."""

    return AppConfig(
        app_name=st.secrets.get(
            "APP_NAME",
            "Empresa Analytics",
        ),
        environment=st.secrets.get(
            "ENVIRONMENT",
            "development",
        ),
        supabase=SupabaseConfig(
            # Se leen con get para que la app arranque en modo local
            # aunque todavía no exista una cuenta de Supabase.
            url=st.secrets.get("SUPABASE_URL", ""),
            key=st.secrets.get("SUPABASE_KEY", ""),
        ),
        auth_enabled=_como_booleano(
            st.secrets.get("AUTH_ENABLED", True)
        ),
        referencias_path=st.secrets.get(
            "REFERENCIAS_PATH",
            "referencias",
        ),
    )