from pathlib import Path

import streamlit as st


MODULES_DIR = (
    Path(__file__).resolve().parent.parent / "modules"
)


def build_navigation() -> list:
    """Construye la navegación principal de la aplicación."""

    return [
        st.Page(
            MODULES_DIR / "home" / "page.py",
            title="Dashboard",
            icon=":material/dashboard:",
            url_path="dashboard",
            default=True,
        ),

        st.Page(
            MODULES_DIR / "contratos" / "page.py",
            title="Contratos",
            icon=":material/description:",
            url_path="contratos",
        ),

        st.Page(
            MODULES_DIR / "herramientas" / "page.py",
            title="Herramientas",
            icon=":material/build:",
            url_path="herramientas",
        ),
        st.Page(
            MODULES_DIR / "tarifas" / "page.py",
            title="Tarifas",
            icon=":material/attach_money:",
            url_path="tarifas",
        ),
        st.Page(
            MODULES_DIR / "prestadores" / "page.py",
            title="Prestadores",
            icon=":material/business:",
            url_path="prestadores",
        ),

        st.Page(
            MODULES_DIR / "cargues" / "page.py",
            title="Cargues GEMANET",
            icon=":material/upload_file:",
            url_path="cargues",
        ),

        st.Page(
            MODULES_DIR / "conciliacion" / "page.py",
            title="Conciliación GEMANET",
            icon=":material/compare_arrows:",
            url_path="conciliacion",
        ),

        st.Page(
            MODULES_DIR / "consulta" / "page.py",
            title="Consulta de documentos",
            icon=":material/find_in_page:",
            url_path="consulta",
        ),

        st.Page(
            MODULES_DIR / "referencias" / "page.py",
            title="Consulta de referencias",
            icon=":material/manage_search:",
            url_path="referencias",
        ),
    ]