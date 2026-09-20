from typing import Any

from src.app.infrastructure.supabase.client import get_supabase_client
from src.app.core.session import (
    clear_session,
    get_current_user,
    set_authenticated_user,
)


class AuthService:
    """Servicio encargado de la autenticación."""

    def __init__(self):
        self.supabase = get_supabase_client()

    def login(
        self,
        email: str,
        password: str,
    ) -> Any:

        response = self.supabase.auth.sign_in_with_password(
            {
                "email": email,
                "password": password,
            }
        )

        if response.user is None:
            raise ValueError(
                "No fue posible autenticar el usuario."
            )

        set_authenticated_user(
            user=response.user,
            auth_session=response.session,
            permissions=set(),
        )

        return response

    def restore_session(self) -> bool:
        """
        Intenta recuperar la sesión existente de Supabase
        después de un refresh/rerun de Streamlit.
        """

        try:
            response = self.supabase.auth.get_session()

            if response is None:
                return False

            session = response

            if session.user is None:
                return False

            set_authenticated_user(
                user=session.user,
                auth_session=session,
                permissions=set(),
            )

            return True

        except Exception:
            clear_session()
            return False

    def logout(self) -> None:
        try:
            self.supabase.auth.sign_out()
        except Exception:
            # Evita que un error de red impida limpiar
            # la sesión local de Streamlit.
            pass
        finally:
            clear_session()


def is_authenticated() -> bool:
    return get_current_user() is not None