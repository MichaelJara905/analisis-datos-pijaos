# Cargues GEMANET

Prepara un anexo tarifario en Excel y genera el TXT del cargue masivo,
señalando lo que hay que revisar antes de subirlo.

## Uso desde la aplicación

Menú **Cargues GEMANET**: subes el anexo, eliges el tipo, revisas cómo se
interpretó y descargas el TXT más los reportes en Excel.

## Uso desde la terminal

```bash
python -m src.app.application.cli_cargues anexo_traumasur.xlsx --tipo INS --salida salidas/
```

| Opción | Para qué |
|---|---|
| `--tipo` | `INS`, `CUMS` o `CUPS` |
| `--hoja` | forzar una hoja cuando la detección falla |
| `--fila-encabezado` | forzar la fila de encabezados (base 1) |
| `--solo-analizar` | ver el resumen sin escribir archivos |

Genera: el TXT, `_hallazgos.csv` (qué se corrigió y qué revisar) y
`_registros.csv` (cada fila con su estado y la línea que produce).
El anexo original nunca se modifica.

## Estructura del TXT

```
CUMS / INS   codigo;valor_o_codigo_ley;tipo;porcentaje;descripcion;norma;
CUPS         codigo;valor_o_codigo_ley;tipo;porcentaje;norma;
```

- Separador `;`, cada registro cierra con `;`
- CRLF entre registros, sin salto al final, sin espacios sobrantes
- Campo 2: el valor si la tarifa es propia, el **código ley** si es regulada
- Tipos válidos: `PRO`, `UVB`, `UVR`, `UVT`
- Porcentaje entero con signo; `0` cuando no hay descuento

## Reglas aplicadas

**Corrige y registra el cambio**

- Tildes y Ñ
- `N°` → `NRO`; `°` suelto → ` GRADOS`
- `Ø ø` → `D` · `º ª` → `O` `A` · `® ™` → `(R)` `(TM)` · `Ф` → se elimina
- `;` → `,`
- Valor redondeado al peso, al estilo de Excel (0,5 sube)
- Porcentaje de fracción a entero: `-0,1` → `-10`

**Bloquea el registro**

- Código vacío o con formato inválido
- Descripción vacía
- Sin tarifa numérica, incluido "BAJO COTIZACION"
- Insumo marcado como tarifa regulada
- Tarifa regulada sin código ley o con código ley mal formado
- Tipo de tarifa "SOAT" sin precisar UVB, UVR o UVT
- Caracteres sin regla de reemplazo

**Avisa, pero genera**

- Códigos duplicados, como los CUPS adulto/pediátrico
- Descripciones repetidas con códigos distintos
- Código leído como número, donde Excel pudo perder ceros a la izquierda
- Tarifa propia con porcentaje distinto de cero

## Cuando aparezca un caso nuevo

Casi todo se ajusta en `src/app/domain/cargues/rules.py`, sin tocar lógica:

- Columna con otro nombre → `ALIAS_DE_COLUMNAS`
- Carácter nuevo que daña el cargue → `REEMPLAZOS_DE_CARACTERES`
- Otro texto que significa "sin tarifa" → `TEXTOS_SIN_TARIFA`

## Archivos

| Archivo | Responsabilidad |
|---|---|
| `domain/cargues/rules.py` | Configuración: formato, caracteres, alias |
| `domain/cargues/parsing.py` | Celda → código, valor entero, porcentaje |
| `domain/cargues/sanitizer.py` | Limpieza de la descripción |
| `domain/cargues/validators.py` | Construcción y validación de registros |
| `domain/cargues/txt_writer.py` | Generación del archivo |
| `infrastructure/excel/anexos.py` | Detección de hoja, encabezados y columnas |
| `application/cargues_service.py` | Orquestación y reportes |
| `modules/cargues/page.py` | Interfaz |
