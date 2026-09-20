# Arquitectura

## Por qué cambió

El proyecto tenía toda la lógica dentro de `modules/tarifas/`, mezclando
interfaz, reglas de negocio y lectura de archivos en los mismos archivos.
Funcionaba, pero para probar una regla había que levantar Streamlit, y la
lógica no se podía reutilizar desde la terminal.

La reorganización sigue las capas que ya proponía el README original
(secciones 23 y 24), llevadas al código.

## Capas

```
src/app/
├── domain/           reglas de negocio — Python puro
│   ├── cargues/      estructura del TXT, validaciones, saneamiento
│   └── tarifas/      normalización de texto
│
├── application/      casos de uso — orquesta, sin Streamlit
│   ├── auth_service.py
│   ├── cargues_service.py
│   ├── referencias_service.py
│   ├── tarifas_service.py
│   └── cli_cargues.py
│
├── infrastructure/   el mundo exterior
│   ├── excel/        anexos.py (lectura de anexos), workbook.py
│   ├── referencias/  repositorio.py (fuentes + caché en disco)
│   └── supabase/     client.py
│
├── modules/          presentación — solo Streamlit
│   ├── auth/ home/ contratos/ herramientas/ prestadores/
│   ├── tarifas/      page.py, charts.py
│   ├── cargues/      page.py
│   └── referencias/  page.py
│
├── components/       layout compartido
├── core/             config, sesión, tema
└── navigation/       menú
```

**La regla es una sola: las dependencias apuntan hacia adentro.**
`modules` puede usar `application`; `application` puede usar `domain` e
`infrastructure`; `domain` no importa nada del proyecto. Por eso el
dominio se prueba sin Streamlit, sin Polars y sin archivos.

## Qué se movió

| Antes | Ahora |
|---|---|
| `auth/service.py` | `application/auth_service.py` |
| `auth/supabase.py` | `infrastructure/supabase/client.py` |
| `modules/tarifas/service.py` | `application/tarifas_service.py` |
| `modules/tarifas/transformations.py` (texto) | `domain/tarifas/text.py` |
| `modules/tarifas/transformations.py` (Polars) | `application/tarifas_service.py` |
| lectura de plantilla y exportación a Excel | `infrastructure/excel/workbook.py` |

`modules/tarifas/page.py` y `charts.py` se quedan donde estaban; solo
cambiaron sus imports. El comportamiento del módulo de tarifas es el mismo.

## Qué se agregó

**Cargues GEMANET** (`domain/cargues`, `infrastructure/excel/anexos.py`,
`application/cargues_service.py`, `modules/cargues/page.py`): prepara un
anexo tarifario y genera el TXT del cargue masivo. Ver `docs/CARGUES.md`.

**Consulta de referencias** (`infrastructure/referencias/repositorio.py`,
`application/referencias_service.py`, `modules/referencias/page.py`):
consulta el Superhomologador, la Circular 022 y Máximos y Mínimos desde
una sola pantalla. Ver `docs/REFERENCIAS.md`.

## Correcciones al código existente

- `sanitize_text` **no se modificó**, pero ya no se usa para los cargues.
  Borra paréntesis, guiones, comas y barras, y eso destruiría las
  referencias de los insumos en un TXT. Para GEMANET existe ahora
  `domain/cargues/sanitizer.py`, con reglas distintas y verificadas.
- Dos erratas de interfaz en la página de tarifas: "Sancar y exportar" y
  "Cruzándo fuentes".

## Cómo aplicarlo

El proyecto viene completo. Sobre una copia limpia del repositorio:

1. Reemplaza `src/`, `tests/`, `streamlit_app.py` y `README.md`.
2. Agrega la carpeta `docs/`.
3. Borra las carpetas viejas si quedaron: `src/app/auth/`,
   `src/app/modules/tarifas/service.py` y `transformations.py`.
4. Corre las pruebas: `pytest`.
5. Levanta la app: `streamlit run streamlit_app.py`.

No se agregó ninguna dependencia: `pyproject.toml` queda igual.
`.streamlit/secrets.toml` no viene incluido, a propósito.

## Verificación hecha

- 56 pruebas en verde (44 de cargues, 12 de referencias), más las de
  tarifas que ya existían y siguen apuntando a las mismas funciones.
- Revisión estática de los 33 módulos: todos los imports internos
  resuelven y no quedaron referencias a las rutas viejas.
- El generador de TXT reproduce byte a byte las líneas de CUMS, INS y
  CUPS que GEMANET ya aceptó.
- La consulta de referencias se probó contra los archivos reales: el CUPS
  441302 cruza con el código ley 18300 y da 1.536.400 en UVB, que es el
  valor del manual.

## Modo local, sin Supabase

En `.streamlit/secrets.toml`:

```toml
AUTH_ENABLED = false
```

La app arranca sin pedir login, con un usuario ficticio en sesión, y no
toca Supabase. Es para trabajar en un computador propio.

Si la aplicación se publica, hay que ponerlo en `true` y configurar
`SUPABASE_URL` y `SUPABASE_KEY`: con el modo local activo, cualquiera que
abra la dirección entra sin credenciales.

Hay una plantilla en `.streamlit/secrets.example.toml`.

## Lo que falta

- **PAQ**: sin soporte. Falta un TXT real para documentar su estructura.
- **Campo "porcentaje de norma"**: va en `0` hasta saber de dónde sale.
- **Proponer el código ley** cuando el CUPS tiene uno solo en el
  homologador: hoy la consulta lo muestra, pero el cargue no lo sugiere.
- **Migrar Supabase a un repositorio**: hoy `auth_service` habla directo
  con el cliente. Funciona, pero lo correcto sería una interfaz en
  `domain` y su implementación en `infrastructure`.
