> **Nota de arquitectura (actualizada).**
> El proyecto se reorganizó en capas: `domain/`, `application/`,
> `infrastructure/` y `modules/`. Las rutas que aparecen más abajo
> corresponden a la estructura anterior. Ver `docs/ARQUITECTURA.md`.

# Empresa Analytics

Plataforma empresarial de análisis de datos orientada al procesamiento,
sanitización, exploración y visualización de información proveniente de
archivos Excel.

El proyecto está diseñado como una aplicación **Streamlit modular**, con
separación de responsabilidades y una estructura preparada para
incorporar lógica de negocio de forma progresiva sin convertir la
interfaz en un bloque monolítico.

---

## 1. Objetivo

Empresa Analytics busca proporcionar una plataforma interna para:

- Cargar información desde archivos Excel.
- Validar y preparar los datos.
- Aplicar filtros dinámicos.
- Sanitizar y transformar columnas seleccionadas.
- Analizar información mediante métricas y gráficos.
- Construir dashboards orientados a procesos empresariales.
- Incorporar nuevos módulos de análisis sin afectar los existentes.
- Mantener autenticación y control de sesión mediante Supabase.
- Centralizar configuración, layout, navegación y servicios de
  infraestructura.

El primer módulo funcional está orientado al **análisis de tarifas**,
pero la arquitectura está pensada para soportar nuevos procesos de
analítica.

---

# 2. Tecnologías

## Aplicación

- **Python 3.13**
- **Streamlit**
- **Supabase**
- **Polars** para procesamiento y transformación de datos.
- **Pandas** cuando sea necesario por compatibilidad con determinadas
  librerías.
- **Plotly** para visualizaciones interactivas.
- **OpenPyXL** para operaciones específicas sobre Excel cuando sea
  necesario.

## Arquitectura

- Arquitectura modular.
- Separación entre presentación, aplicación, dominio e
  infraestructura.
- Servicios para encapsular casos de uso.
- Configuración centralizada.
- Manejo de sesión independiente de la interfaz.
- Autenticación delegada a Supabase.

---

# 3. Arquitectura general

La aplicación sigue una estructura inspirada en principios de
**arquitectura hexagonal / Clean Architecture**, adaptada al contexto de
Streamlit.

La idea principal es evitar que la lógica de negocio dependa
directamente de Streamlit.

```text
                    ┌─────────────────────────┐
                    │       Streamlit UI      │
                    │ Pages / Components      │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │      Application        │
                    │ Services / Use Cases    │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │         Domain          │
                    │ Rules / Models / Logic  │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │     Infrastructure      │
                    │ Supabase / Excel / DB   │
                    └─────────────────────────┘
```

### Regla principal

La interfaz debe encargarse principalmente de:

- Recibir entradas.
- Mostrar información.
- Manejar interacción.
- Invocar servicios.

La lógica de negocio debe permanecer fuera de las páginas Streamlit.

---

# 4. Estructura del proyecto

Una estructura base esperada es:

```text
analisis-contratacion/
│
├── streamlit_app.py
├── README.md
├── pyproject.toml
├── poetry.lock
├── .gitignore
│
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml
│
├── src/
│   └── app/
│       │
│       ├── auth/
│       │   ├── __init__.py
│       │   ├── service.py
│       │   └── supabase.py
│       │
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   └── session.py
│       │
│       ├── components/
│       │   ├── __init__.py
│       │   ├── layout.py
│       │   ├── charts.py
│       │   └── ...
│       │
│       ├── navigation/
│       │   ├── __init__.py
│       │   └── pages.py
│       │
│       ├── modules/
│       │   │
│       │   ├── auth/
│       │   │   └── login.py
│       │   │
│       │   ├── home/
│       │   │   └── page.py
│       │   │
│       │   ├── contratos/
│       │   │   └── page.py
│       │   │
│       │   ├── tarifas/
│       │   │   └── page.py
│       │   │
│       │   └── herramientas/
│       │       └── page.py
│       │
│       ├── application/
│       │   └── ...
│       │
│       ├── domain/
│       │   └── ...
│       │
│       └── infrastructure/
│           └── ...
│
└── tests/
    ├── unit/
    └── integration/
```

Los nombres pueden evolucionar conforme crezca el proyecto, pero la
separación de responsabilidades debe mantenerse.

---

# 5. Punto de entrada

El archivo:

```text
streamlit_app.py
```

es el punto de entrada de Streamlit.

Sus responsabilidades son:

1.  Configurar la aplicación.
2.  Inicializar la sesión.
3.  Verificar autenticación.
4.  Mostrar la página de login cuando no existe una sesión válida.
5.  Construir la navegación autenticada.
6.  Ejecutar la página seleccionada.

Conceptualmente:

```python
def main():
    configure_app()
    initialize_session()

    if not is_authenticated():
        # navegación de autenticación
        return

    render_app_layout()

    pages = build_navigation()
    pg = st.navigation(pages)
    pg.run()
```

No se debe introducir lógica de negocio de módulos en este archivo.

---

# 6. Configuración

La configuración se centraliza mediante `AppConfig` y `SupabaseConfig`.

Ejemplo conceptual:

```python
@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    key: str


@dataclass(frozen=True)
class AppConfig:
    app_name: str
    environment: str
    supabase: SupabaseConfig
```

La configuración se obtiene mediante:

```python
st.secrets
```

Ejemplo:

```toml
APP_NAME = "Empresa Analytics"
ENVIRONMENT = "development"

SUPABASE_URL = "https://xxxxx.supabase.co"
SUPABASE_KEY = "xxxxx"
```

El archivo de secretos **no debe subirse al repositorio**.

Debe estar incluido en `.gitignore`.

---

# 7. Supabase

Supabase se utiliza principalmente como proveedor de autenticación.

La aplicación utiliza:

```text
Supabase Auth
       │
       ▼
Correo + contraseña
       │
       ▼
Usuario autenticado
       │
       ▼
Sesión de Streamlit
```

## Usuario de prueba

Los usuarios se crean desde:

```text
Supabase
→ Authentication
→ Users
```

Se puede crear un usuario con:

```text
Email: usuario@empresa.com
Password: ********
```

Ese usuario posteriormente puede utilizarse desde la pantalla de login.

---

# 8. Autenticación

La autenticación está encapsulada en:

```text
src/app/auth/service.py
```

El servicio tiene responsabilidades como:

```python
login(email, password)
logout()
is_authenticated()
```

Ejemplo conceptual:

```python
response = supabase.auth.sign_in_with_password(
    {
        "email": email,
        "password": password,
    }
)
```

Después de una autenticación correcta, la sesión se registra mediante el
componente de sesión.

La página Streamlit no debe implementar directamente toda la lógica de
Supabase.

---

# 9. Gestión de sesión

La sesión se centraliza en:

```text
src/app/core/session.py
```

Debe manejar como mínimo:

- Inicialización.
- Usuario actual.
- Sesión de Supabase.
- Permisos.
- Limpieza de sesión.

Conceptualmente:

```text
st.session_state
│
├── authenticated_user
├── auth_session
├── permissions
└── ...
```

La inicialización debe ser idempotente: ejecutarla nuevamente no debe
destruir una sesión válida.

Esto es importante porque Streamlit vuelve a ejecutar el script ante
acciones como:

- F5.
- Ctrl + R.
- Interacción con widgets.
- Navegación entre páginas.

---

# 10. Layout global

El layout está ubicado en:

```text
src/app/components/layout.py
```

Actualmente centraliza:

- CSS global.
- Encabezado.
- Información del usuario.
- Cerrar sesión.
- Elementos generales del sidebar.
- Estructura visual común.

Ejemplo:

```python
def render_app_layout():
    inject_global_css()
    render_user_section()
```

La intención es que cada módulo se concentre en su contenido y no tenga
que repetir:

- CSS.
- Header.
- Usuario.
- Logout.
- Estructura común.

---

# 11. Temas

El proyecto utiliza el sistema de temas de Streamlit mediante:

```text
.streamlit/config.toml
```

Se pueden definir configuraciones como:

```toml
[theme]
base = "light"
primaryColor = "#2563EB"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F8FAFC"
textColor = "#172033"
font = "sans serif"
```

Para modo oscuro:

```toml
[theme]
base = "dark"
primaryColor = "#3B82F6"
backgroundColor = "#0F172A"
secondaryBackgroundColor = "#1E293B"
textColor = "#F8FAFC"
font = "sans serif"
```

El CSS personalizado debe diseñarse de forma compatible con ambos temas.

No se recomienda fijar innecesariamente colores blancos u oscuros
directamente en componentes que deban soportar ambos modos.

---

# 12. Navegación

La navegación se centraliza en:

```text
src/app/navigation/pages.py
```

Ejemplo:

```python
def build_navigation():
    return [
        st.Page(
            "src/app/modules/home/page.py",
            title="Dashboard",
            icon=":material/dashboard:",
            default=True,
        ),
        st.Page(
            "src/app/modules/contratos/page.py",
            title="Contratos",
            icon=":material/description:",
        ),
        st.Page(
            "src/app/modules/tarifas/page.py",
            title="Tarifas",
            icon=":material/price_change:",
        ),
    ]
```

Cada página debe tener un pathname único.

Es importante evitar registrar dos páginas que Streamlit interprete con
el mismo pathname.

---

# 13. Módulo de tarifas

El módulo de tarifas es uno de los primeros módulos funcionales.

Ubicación:

```text
src/app/modules/tarifas/
```

El objetivo es analizar información reportada mediante una plantilla
Excel.

Flujo general:

```text
Excel
  │
  ▼
Carga
  │
  ▼
Validación
  │
  ▼
Normalización
  │
  ▼
Sanitización
  │
  ▼
Filtros dinámicos
  │
  ├───────────────┐
  ▼               ▼
Métricas       Gráficos
  │               │
  └───────┬───────┘
          ▼
       Análisis
```

---

# 14. Carga de Excel

La interfaz permitirá seleccionar un archivo:

```python
uploaded_file = st.file_uploader(
    "Cargar archivo",
    type=["xlsx", "xls"],
)
```

La carga no debe convertirse inmediatamente en lógica de negocio.

Se recomienda crear un servicio encargado de:

```text
Excel → DataFrame/Polars DataFrame
```

Por ejemplo:

```text
application/tarifas/
    service.py
```

o, si el proyecto crece:

```text
domain/tarifas/
infrastructure/excel/
```

---

# 15. Procesamiento con Polars

Para operaciones intensivas de transformación se priorizará **Polars**.

Ejemplo conceptual:

```python
import polars as pl

df = pl.read_excel(...)
```

Las operaciones de:

- Filtrado.
- Selección de columnas.
- Transformación.
- Normalización.
- Agrupación.
- Agregación.

deben ejecutarse preferiblemente con Polars cuando sea conveniente.

Esto permite mantener una separación clara entre:

```text
UI
↓
Servicio de análisis
↓
Polars
```

---

# 16. Sanitización de datos

Una funcionalidad importante del módulo de tarifas será permitir
seleccionar columnas y aplicar transformaciones.

Ejemplo:

```text
Descripción
---------------------------------
"Medicamento ÑÁÑÉ #123 / ABC"
```

Después:

```text
"Medicamento NANAE 123 ABC"
```

Las transformaciones pueden incluir:

- Eliminación de caracteres especiales.
- Normalización de espacios.
- Conversión de mayúsculas/minúsculas.
- Eliminación o reemplazo de tildes.
- Normalización de caracteres Unicode.
- Eliminación de símbolos no deseados.
- Limpieza de saltos de línea.
- Conversión de valores nulos.
- Normalización de textos.

La sanitización debe implementarse como lógica reutilizable y no
directamente dentro de la página Streamlit.

---

# 17. Transformaciones configurables

La interfaz debe permitir seleccionar:

```text
Columnas
    ↓
Transformaciones
    ├── Normalizar texto
    ├── Quitar tildes
    ├── Quitar símbolos
    ├── Normalizar espacios
    ├── Mayúsculas
    ├── Minúsculas
    └── ...
```

Esto permitirá extender posteriormente el sistema con nuevas
transformaciones.

Una posible abstracción:

```python
class TextTransformation:
    def apply(self, value: str) -> str:
        ...
```

Y posteriormente:

```text
RemoveAccentsTransformation
RemoveSpecialCharactersTransformation
NormalizeWhitespaceTransformation
UpperCaseTransformation
```

---

# 18. Filtros dinámicos

El módulo deberá detectar las columnas disponibles y permitir construir
filtros.

Ejemplo:

```text
Filtros

Año             [2026 ▼]
Mes             [Agosto ▼]
Contrato        [Todos ▼]
Tipo tarifa     [Todos ▼]
Estado          [Activo ▼]
```

Los filtros deben afectar tanto:

- La tabla.
- Las métricas.
- Los gráficos.

La idea es trabajar sobre un conjunto de datos filtrado común.

```text
Dataset original
       │
       ▼
Filtros
       │
       ▼
Dataset filtrado
       ├── KPIs
       ├── Tabla
       └── Gráficos
```

---

# 19. Gráficos

Los gráficos deben ser componentes reutilizables.

Ubicación sugerida:

```text
src/app/components/charts.py
```

Ejemplo:

```python
def render_bar_chart(
    data,
    x,
    y,
    title=None,
):
    ...
```

Se pueden utilizar gráficos de:

- Barras.
- Líneas.
- Pastel/donut cuando tenga sentido.
- Histograma.
- Dispersión.
- Series temporales.
- Boxplot.
- Heatmap.

Se priorizará **Plotly** para permitir interacción.

---

# 20. Gráficos estándar del proceso

El módulo de tarifas debe comenzar con un conjunto de visualizaciones
estándar.

Ejemplos:

### Distribución por tarifa

```text
Tarifa
│
├── 100
├── 200
├── 300
└── ...
```

### Cantidad de registros por categoría

```text
Categoría → cantidad
```

### Evolución temporal

```text
Mes → cantidad / valor
```

### Distribución de valores

Permite detectar:

- Valores extremos.
- Concentraciones.
- Registros atípicos.

### Ranking

Por ejemplo:

```text
Top conceptos
Top contratos
Top tarifas
Top categorías
```

Los gráficos exactos dependerán de las columnas presentes en la
plantilla Excel.

---

# 21. Dashboard

El dashboard deberá seguir una estructura aproximadamente así:

```text
┌───────────────────────────────────────────────┐
│                 TARIFAS                       │
│ Análisis de información reportada             │
└───────────────────────────────────────────────┘

┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐
│ Registros│ │ Tarifas  │ │ Contratos│ │ Valor  │
└──────────┘ └──────────┘ └──────────┘ └────────┘

┌────────────────────────┐ ┌─────────────────────┐
│ Distribución tarifas   │ │ Registros categoría │
│                        │ │                     │
└────────────────────────┘ └─────────────────────┘

┌────────────────────────┐ ┌─────────────────────┐
│ Evolución temporal     │ │ Ranking              │
│                        │ │                     │
└────────────────────────┘ └─────────────────────┘

┌───────────────────────────────────────────────┐
│ Datos filtrados                               │
└───────────────────────────────────────────────┘
```

---

# 22. Componentes

Los componentes deben ser reutilizables.

Ejemplos:

```text
components/
├── layout.py
├── charts.py
├── filters.py
├── metrics.py
├── tables.py
├── uploader.py
└── feedback.py
```

No todos tienen que crearse desde el inicio.

Se incorporarán conforme aparezcan necesidades reales.

---

# 23. Separación entre UI y negocio

Evitar:

```python
def page():
    # 300 líneas de procesamiento
    # SQL
    # sanitización
    # agrupaciones
    # cálculos
    # gráficos
```

Preferir:

```python
def page():

    data = upload_file()

    result = tarifas_service.analyze(data)

    render_metrics(result)
    render_charts(result)
    render_table(result)
```

Esto facilita:

- Pruebas.
- Mantenimiento.
- Reutilización.
- Evolución.
- Optimización.

---

# 24. Capas recomendadas

## Presentation

```text
modules/
components/
```

Responsable de:

- Streamlit.
- Formularios.
- Widgets.
- Tablas.
- Gráficos.
- Navegación.

## Application

```text
application/
```

Responsable de:

- Casos de uso.
- Orquestación.
- Flujos de procesamiento.

Ejemplo:

```text
AnalizarTarifasService
```

## Domain

```text
domain/
```

Responsable de:

- Reglas de negocio.
- Entidades.
- Value Objects.
- Validaciones.
- Transformaciones conceptuales.

## Infrastructure

```text
infrastructure/
```

Responsable de:

- Excel.
- Supabase.
- Bases de datos.
- Servicios externos.
- Implementaciones técnicas.

---

# 25. Seguridad

Nunca colocar secretos directamente en:

```python
SUPABASE_KEY = "..."
```

ni subir:

```text
.streamlit/secrets.toml
```

al repositorio.

Utilizar:

```python
st.secrets["SUPABASE_KEY"]
```

El `SUPABASE_KEY` utilizado por una aplicación cliente debe evaluarse
según el modelo de seguridad de Supabase y las políticas RLS
configuradas.

Las claves privilegiadas de servidor no deben exponerse al frontend.

---

# 26. Variables de entorno / secrets

Configuración mínima:

```toml
APP_NAME = "Empresa Analytics"
ENVIRONMENT = "development"

SUPABASE_URL = "https://xxxxx.supabase.co"
SUPABASE_KEY = "xxxxx"
```

Para producción deberán utilizarse secretos administrados por el entorno
de despliegue.

---

# 27. Ejecución local

Activar el entorno virtual:

### PowerShell

```powershell
.venv\Scripts\Activate.ps1
```

Ejecutar Streamlit:

```powershell
streamlit run streamlit_app.py
```

También puede utilizarse:

```powershell
python -m streamlit run streamlit_app.py
```

La aplicación estará disponible normalmente en:

```text
http://localhost:8501
```

---

# 28. Depuración en VS Code

Para depurar Streamlit se recomienda lanzar Streamlit como módulo de
Python.

Configuración sugerida:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Streamlit: Debug",
      "type": "debugpy",
      "request": "launch",
      "module": "streamlit",
      "args": ["run", "${workspaceFolder}/streamlit_app.py"],
      "console": "integratedTerminal"
    }
  ]
}
```

Esto permite utilizar breakpoints dentro de:

```text
src/app/
```

y seguir la ejecución desde el navegador.

---

# 29. Pruebas

Se recomienda crear pruebas separadas por responsabilidad:

```text
tests/
├── unit/
│   ├── auth/
│   ├── tarifas/
│   ├── transformations/
│   └── ...
│
└── integration/
    ├── supabase/
    └── excel/
```

Las reglas de negocio deben poder probarse sin levantar Streamlit.

Por ejemplo:

```python
def test_remove_accents():
    ...
```

---

# 30. Rendimiento

Principios importantes:

### No procesar innecesariamente

Evitar recalcular el mismo dataset en cada interacción.

Utilizar mecanismos de caché de Streamlit cuando corresponda:

```python
@st.cache_data
def process_data(...):
    ...
```

Para recursos compartidos:

```python
@st.cache_resource
def get_resource(...):
    ...
```

### Procesamiento vectorizado

Preferir operaciones de Polars sobre ciclos Python cuando sea posible.

### Separar carga y transformación

```text
Carga
  ↓
Cache
  ↓
Transformación
  ↓
Filtros
  ↓
Visualización
```

---

# 31. Estado de la sesión

No utilizar `st.session_state` indiscriminadamente desde todos los
módulos.

Debe existir una estrategia clara para:

- Autenticación.
- Dataset cargado.
- Filtros.
- Configuración de visualizaciones.
- Estado temporal de la interfaz.

Esto evita dependencias ocultas entre páginas.

---

# 32. Convenciones de código

Se recomienda:

- `snake_case` para funciones y variables.
- `PascalCase` para clases.
- Type hints.
- Docstrings para servicios públicos.
- Funciones pequeñas.
- Evitar lógica duplicada.
- No colocar consultas o reglas de negocio directamente en páginas.
- No utilizar variables globales mutables para estado de usuario.

Ejemplo:

```python
def sanitize_column(
    data: pl.DataFrame,
    column: str,
) -> pl.DataFrame:
    ...
```

---

# 33. Flujo de desarrollo

El desarrollo se realizará progresivamente.

## Fase 1 --- Base técnica

- [x] Proyecto Streamlit.
- [x] Configuración.
- [x] Supabase.
- [x] Login.
- [x] Sesión persistente durante reruns.
- [x] Logout.
- [x] Navegación.
- [x] Layout global.
- [x] Tema claro/oscuro.
- [x] Dashboard base.

## Fase 2 --- Componentes

- [ ] Componente de carga Excel.
- [ ] Componente de métricas.
- [ ] Componente de tablas.
- [ ] Componente de gráficos.
- [ ] Componente de filtros.
- [ ] Sistema de mensajes/feedback.

## Fase 3 --- Tarifas

- [ ] Definir plantilla Excel.
- [ ] Lectura del archivo.
- [ ] Validación de columnas.
- [ ] Normalización.
- [ ] Sanitización.
- [ ] Filtros dinámicos.
- [ ] KPIs.
- [ ] Gráficos estándar.
- [ ] Tabla de resultados.
- [ ] Exportación de resultados.

## Fase 4 --- Arquitectura de negocio

- [ ] Servicios de aplicación.
- [ ] Reglas de dominio.
- [ ] Modelos.
- [ ] Validadores.
- [ ] Tests unitarios.
- [ ] Tests de integración.

## Fase 5 --- Producción

- [ ] Configuración de producción.
- [ ] Gestión segura de secretos.
- [ ] Docker.
- [ ] Logging.
- [ ] Monitoreo.
- [ ] Optimización.
- [ ] CI/CD.

---

# 34. Principio de evolución

La aplicación debe crecer desde una base funcional pequeña hacia una
plataforma modular.

No se deben crear abstracciones complejas antes de necesitarlas.

La prioridad es:

```text
Funcionalidad
     ↓
Separación de responsabilidades
     ↓
Reutilización
     ↓
Optimización
     ↓
Escalabilidad
```

Cada nuevo módulo debe seguir el mismo patrón:

```text
modules/<modulo>/
        │
        └── page.py

application/
        │
        └── servicios del módulo

domain/
        │
        └── reglas del módulo

infrastructure/
        │
        └── fuentes externas
```

---

# 35. Próximo objetivo

El siguiente objetivo técnico es completar el **módulo de análisis de
tarifas** partiendo de una plantilla Excel real.

El flujo esperado es:

```text
Usuario
  │
  ▼
Carga Excel
  │
  ▼
Validación de estructura
  │
  ▼
Normalización
  │
  ▼
Dataset Polars
  │
  ├───────────────┐
  ▼               ▼
Filtros       Sanitización
  │               │
  └───────┬───────┘
          ▼
    Dataset analítico
          │
    ┌─────┼──────────┐
    ▼     ▼          ▼
  KPIs  Gráficos   Tabla
          │
          ▼
       Análisis
```

La lógica de negocio se implementará sobre esta base sin modificar
innecesariamente la arquitectura existente.

---

# 36. Principios arquitectónicos resumidos

1.  **Streamlit es la capa de presentación, no la capa de negocio.**
2.  **Supabase se utiliza como infraestructura de autenticación.**
3.  **La sesión se administra centralmente.**
4.  **Los módulos deben ser independientes.**
5.  **Los componentes visuales deben ser reutilizables.**
6.  **Polars será la herramienta principal para procesamiento tabular.**
7.  **Las transformaciones de datos deben ser reutilizables y
    testeables.**
8.  **Los secretos nunca se almacenan en código fuente.**
9.  **Las reglas de negocio deben poder probarse sin Streamlit.**
10. **La arquitectura debe evolucionar según las necesidades reales del
    proyecto.**

---

## Licencia

Proyecto de uso interno/empresarial.

La licencia y condiciones de distribución deberán definirse antes de
realizar una distribución externa.
