import streamlit as st

from src.app.application.auth_service import (
    AuthService,
    is_authenticated,
)
from src.app.components.layout import render_app_layout
from src.app.core.config import get_config
from src.app.core.session import initialize_session, set_authenticated_user
from src.app.navigation.pages import build_navigation


def configure_app() -> None:
    """Configura los parámetros generales de la aplicación."""

    st.set_page_config(
        page_title="Empresa Analytics",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )


class UsuarioLocal:
    """Usuario ficticio para trabajar sin Supabase."""

    email = "modo local"


def restore_authentication() -> None:
    """Restaura la sesión, o entra en modo local si no hay autenticación."""

    if is_authenticated():
        return

    if not get_config().auth_enabled:
        set_authenticated_user(
            user=UsuarioLocal(),
            auth_session=None,
            permissions=set(),
        )
        return

    AuthService().restore_session()


def main() -> None:
    """Punto de entrada principal de la aplicación."""

    configure_app()

    initialize_session()

    # Intentar recuperar una sesión existente
    # después de un refresh del navegador.
    restore_authentication()

    if not is_authenticated():

        login_page = st.Page(
            "src/app/modules/auth/login.py",
            title="Iniciar sesión",
            icon=":material/login:",
            default=True,
        )

        pg = st.navigation([login_page])
        
        pg.run()

        return

    # ---------------------------------------------------------
    # Aplicación autenticada
    # ---------------------------------------------------------

    render_app_layout()

    pages = build_navigation()

    pg = st.navigation(pages)

    pg.run()


if __name__ == "__main__":
    main()