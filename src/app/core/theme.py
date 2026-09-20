from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class Theme:
    """Configuración visual de un tema."""

    name: str
    label: str

    primary: str
    background: str
    surface: str
    border: str
    text: str
    text_secondary: str


THEMES: dict[str, Theme] = {
    "light": Theme(
        name="light",
        label="☀️ Claro",
        primary="#2563EB",
        background="#FFFFFF",
        surface="#F8FAFC",
        border="#E5E7EB",
        text="#172033",
        text_secondary="#64748B",
    ),
    "dark": Theme(
        name="dark",
        label="🌙 Oscuro",
        primary="#60A5FA",
        background="#0F172A",
        surface="#1E293B",
        border="#334155",
        text="#F8FAFC",
        text_secondary="#CBD5E1",
    ),
}


def get_current_theme() -> Theme:
    """Obtiene el tema actual."""

    theme_name = st.session_state.get(
        "theme",
        "light",
    )

    return THEMES.get(
        theme_name,
        THEMES["light"],
    )


def set_theme(theme_name: str) -> None:
    """Cambia el tema actual."""

    if theme_name not in THEMES:
        raise ValueError(
            f"Tema no soportado: {theme_name}"
        )

    st.session_state["theme"] = theme_name


def render_theme_selector() -> None:
    """Renderiza el selector de tema."""

    current_theme = get_current_theme()

    theme_names = list(THEMES.keys())

    current_index = theme_names.index(
        current_theme.name
    )

    selected_theme = st.sidebar.selectbox(
        "Tema",
        options=theme_names,
        index=current_index,
        format_func=lambda name: THEMES[name].label,
        key="theme_selector",
    )

    if selected_theme != current_theme.name:
        set_theme(selected_theme)
        st.rerun()