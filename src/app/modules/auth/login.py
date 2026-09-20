import streamlit as st

from src.app.application.auth_service import AuthService


def render_login() -> None:

    st.markdown(
        """
        <div style="text-align:center;">
            <h1>Empresa Analytics</h1>
            <p>Plataforma empresarial de analítica</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("")

    _, center, _ = st.columns([1, 2, 1])

    with center:

        st.subheader("Iniciar sesión")

        with st.form("login_form"):

            email = st.text_input(
                "Correo electrónico",
                placeholder="usuario@empresa.com",
            )

            password = st.text_input(
                "Contraseña",
                type="password",
            )

            submitted = st.form_submit_button(
                "Ingresar",
                use_container_width=True,
            )

            if submitted:

                if not email or not password:
                    st.error(
                        "Ingrese correo y contraseña."
                    )
                    return

                try:

                    AuthService().login(
                        email=email,
                        password=password,
                    )

                    st.success(
                        "Inicio de sesión exitoso."
                    )

                    st.rerun()

                except Exception:
                    st.error(
                        "Correo o contraseña incorrectos."
                    )


render_login()