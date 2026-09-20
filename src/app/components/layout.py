import streamlit as st

from src.app.application.auth_service import AuthService
from src.app.core.config import get_config
from src.app.core.session import get_current_user

APP_NAME = "Empresa Analytics"


# ============================================================
# THEMES
# ============================================================

THEMES = {
    "Claro": {
        "background": "#ffffff",
        "surface": "#ffffff",
        "surface_secondary": "#f8fafc",
        "sidebar": "#f8fafc",
        "border": "#e2e8f0",
        "text": "#172033",
        "text_secondary": "#64748b",
        "primary": "#2563eb",
        "primary_soft": "#eff6ff",
        "hover": "#f1f5f9",
        "shadow": "rgba(0, 0, 0, 0.04)",
    },
    "Oscuro": {
        "background": "#0f172a",
        "surface": "#111827",
        "surface_secondary": "#1e293b",
        "sidebar": "#1e293b",
        "border": "#334155",
        "text": "#f8fafc",
        "text_secondary": "#94a3b8",
        "primary": "#60a5fa",
        "primary_soft": "#172554",
        "hover": "#273449",
        "shadow": "rgba(0, 0, 0, 0.25)",
    },
}


# ============================================================
# THEME
# ============================================================

def get_current_theme() -> str:
    """Obtiene el tema seleccionado actualmente."""

    return st.session_state.get(
        "theme",
        "Claro",
    )


def render_theme_selector() -> None:
    """Renderiza el selector de tema en el sidebar."""

    current_theme = get_current_theme()

    selected_theme = st.sidebar.selectbox(
        "Tema",
        options=list(THEMES.keys()),
        index=list(THEMES.keys()).index(current_theme),
        key="theme_selector",
    )

    if selected_theme != current_theme:
        st.session_state["theme"] = selected_theme
        st.rerun()


# ============================================================
# GLOBAL CSS
# ============================================================

def inject_global_css() -> None:
    """Inyecta los estilos globales según el tema seleccionado."""

    theme = THEMES[get_current_theme()]

    st.markdown(
        f"""
        <style>

        /* =====================================================
           VARIABLES DEL TEMA
           ===================================================== */

        :root {{
            --app-background: {theme["background"]};
            --app-surface: {theme["surface"]};
            --app-surface-secondary: {theme["surface_secondary"]};
            --app-sidebar: {theme["sidebar"]};
            --app-border: {theme["border"]};
            --app-text: {theme["text"]};
            --app-text-secondary: {theme["text_secondary"]};
            --app-primary: {theme["primary"]};
            --app-primary-soft: {theme["primary_soft"]};
            --app-hover: {theme["hover"]};
            --app-shadow: {theme["shadow"]};
        }}


        /* =====================================================
           GLOBAL
           ===================================================== */

        .stApp {{
            background-color: var(--app-background);
            color: var(--app-text);
        }}


        /* =====================================================
           MAIN CONTENT
           ===================================================== */

        .block-container {{
            padding-top: 2rem;
            padding-bottom: 3rem;
            padding-left: 3rem;
            padding-right: 3rem;
            max-width: 1600px;
        }}


        /* =====================================================
           SIDEBAR
           ===================================================== */

        section[data-testid="stSidebar"] {{
            background-color: var(--app-sidebar);
            border-right: 1px solid var(--app-border);
        }}

        section[data-testid="stSidebar"] > div {{
            padding-top: 1rem;
        }}


        /* =====================================================
           HEADER
           ===================================================== */

        .app-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;

            width: 100%;

            padding-bottom: 1rem;
            margin-bottom: 1.5rem;

            border-bottom: 1px solid var(--app-border);
        }}

        .app-header-title {{
            font-size: 1.6rem;
            font-weight: 700;
            color: var(--app-text);
            margin: 0;
        }}

        .app-header-subtitle {{
            font-size: 0.85rem;
            color: var(--app-text-secondary);
            margin-top: 0.25rem;
        }}


        /* =====================================================
           CARDS
           ===================================================== */

        .metric-card {{
            background: var(--app-surface);
            border: 1px solid var(--app-border);
            border-radius: 12px;

            padding: 1.25rem;

            box-shadow: 0 1px 2px var(--app-shadow);
        }}


        /* =====================================================
           TEXTOS
           ===================================================== */

        .app-text {{
            color: var(--app-text);
        }}

        .app-text-secondary {{
            color: var(--app-text-secondary);
        }}


        /* =====================================================
           STREAMLIT ELEMENTS
           ===================================================== */

        [data-testid="stMarkdownContainer"] {{
            color: var(--app-text);
        }}


        /* =====================================================
           INPUTS
           ===================================================== */

        div[data-baseweb="select"] > div {{
            background-color: var(--app-surface);
            border-color: var(--app-border);
        }}


        /* =====================================================
           BOTONES
           ===================================================== */

        .stButton > button {{
            background-color: var(--app-surface);
            color: var(--app-text);
            border: 1px solid var(--app-border);
        }}

        .stButton > button:hover {{
            border-color: var(--app-primary);
            color: var(--app-primary);
        }}


        /* =====================================================
           OCULTAR ELEMENTOS INNECESARIOS
           ===================================================== */

        #MainMenu {{
            visibility: hidden;
        }}

        footer {{
            visibility: hidden;
        }}


        /* =====================================================
           RESPONSIVE
           ===================================================== */

        @media (max-width: 768px) {{

            .block-container {{
                padding-left: 1rem;
                padding-right: 1rem;
            }}

            .app-header-title {{
                font-size: 1.3rem;
            }}

        }}

        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# HEADER
# ============================================================

def render_header(
    title: str | None = None,
    subtitle: str | None = None,
) -> None:
    """
    Renderiza el encabezado global de la aplicación.
    """

    page_title = title or APP_NAME

    page_subtitle = subtitle or (
        "Plataforma empresarial de analítica"
    )

    st.html(
        f"""
        <div class="app-header">

            <div>

                <div class="app-header-title">
                    {page_title}
                </div>

                <div class="app-header-subtitle">
                    {page_subtitle}
                </div>

            </div>

        </div>
        """,
    )


# ============================================================
# USER
# ============================================================

def render_user_section() -> None:
    """Renderiza la información del usuario y acciones."""

    user = get_current_user()

    if user is None:
        return

    st.sidebar.divider()

    st.sidebar.caption("APARIENCIA")

    render_theme_selector()

    st.sidebar.divider()

    st.sidebar.caption("USUARIO")

    email = getattr(user, "email", None)

    if email:
        st.sidebar.write(f"👤 {email}")

    # En modo local no hay sesión que cerrar.
    if not get_config().auth_enabled:
        st.sidebar.caption("Sin autenticación (modo local)")
        return

    if st.sidebar.button(
        "Cerrar sesión",
        use_container_width=True,
        type="secondary",
    ):
        AuthService().logout()
        st.rerun()


# ============================================================
# APP LAYOUT
# ============================================================

def render_app_layout() -> None:
    """
    Inicializa el layout global de la aplicación.
    """

    # Primero se aplica el CSS correspondiente
    # al tema actual.
    inject_global_css()

    # Después se renderiza la sección lateral.
    render_user_section()
