import streamlit as st

USER_KEY = "auth_user"
SESSION_KEY = "auth_session"
PERMISSIONS_KEY = "permissions"


def initialize_session() -> None:
    """
    Inicializa el estado de autenticación de Streamlit.

    No sobrescribe valores existentes.
    """

    defaults = {
        USER_KEY: None,
        SESSION_KEY: None,
        PERMISSIONS_KEY: set(),
    }

    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


def set_authenticated_user(
    user,
    auth_session,
    permissions: set[str] | None = None,
) -> None:
    """
    Guarda la información del usuario autenticado
    en el estado de Streamlit.
    """

    st.session_state[USER_KEY] = user
    st.session_state[SESSION_KEY] = auth_session
    st.session_state[PERMISSIONS_KEY] = (
        set(permissions) if permissions is not None else set()
    )


def get_current_user():
    """
    Obtiene el usuario autenticado.

    Retorna None si no existe una sesión autenticada.
    """

    return st.session_state.get(USER_KEY)


def get_auth_session():
    """
    Obtiene la sesión actual de Supabase.

    Retorna None si no existe una sesión.
    """

    return st.session_state.get(SESSION_KEY)


def get_permissions() -> set[str]:
    """
    Obtiene los permisos del usuario autenticado.

    Siempre retorna un set independiente para evitar
    modificaciones accidentales del estado.
    """

    permissions = st.session_state.get(
        PERMISSIONS_KEY,
        set(),
    )

    return set(permissions)


def is_authenticated() -> bool:
    """
    Determina si existe un usuario autenticado.
    """

    return get_current_user() is not None


def clear_session() -> None:
    """
    Limpia completamente el estado de autenticación.
    """

    st.session_state[USER_KEY] = None
    st.session_state[SESSION_KEY] = None
    st.session_state[PERMISSIONS_KEY] = set()