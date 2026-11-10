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
- Traslado o propio (`PRO####`) marcado como regulado
- Con homologador: `PRO` con un SOAT como valor, o código ley no homologado
- Tipo de tarifa "SOAT" sin precisar UVB, UVR o UVT
- Caracteres sin regla de reemplazo

**Avisa, pero genera**

- Códigos duplicados, como los CUPS adulto/pediátrico
- Descripciones repetidas con códigos distintos
- Código leído como número, donde Excel pudo perder ceros a la izquierda
- Tarifa propia con porcentaje distinto de cero

## Validación de CUPS contra el homologador

Con `--referencias CARPETA` (CLI) o `REFERENCIAS_PATH` (pantalla), el
cargue CUPS se cruza con la hoja HOMOLOGADOR del SUPERHOMOLOGADOR:

| Caso | Resultado |
|---|---|
| Tarifa `PRO` cuyo valor es un SOAT homologado a ese CUPS | **Bloquea** (es el código ley cargado como valor) |
| Tarifa regulada con un código ley que no es homologado de ese CUPS | **Bloquea** (el homólogo debe ser igual; basta con uno de los varios que tenga) |
| CUPS que el homologador no conoce | No se marca; el reporte dice cuántos no se pudieron cruzar |
| Sin carpeta de referencias | Hallazgo general: "no se validó contra el homologador" |

Límite conocido: un `PRO` con un valor que *parece* SOAT pero corresponde a
otro código no se detecta; solo se compara contra los SOAT de ese CUPS.

## Códigos CUPS, propios y traslados

- CUPS: 6 caracteres `[0-9A-Z]` (casi siempre dígitos; a veces letras,
  como `129M01` o `601T02`) o un propio `PRO####`.
- Los **traslados** (`601T01`, `601T02`, `602T01`, `602T02`) y los
  **propios** nunca llevan SOAT: con `UVB`, `UVT` o `UVR` el registro se bloquea.
- Un CUPS de 5 dígitos se bloquea y el mensaje sugiere el cero inicial
  perdido por Excel; nunca se corrige solo.
- `_propios_pendientes.csv` junta los registros cuyo anexo dice "crear
  propio" y los traslados. **El sistema no crea nada**: solo los separa.

## Creación de propios

```bash
python -m src.app.application.cli_propios propios.xlsx --ultimo-pro PRO5715 --salida salidas/
```

`propios.xlsx` (o `.csv`) trae NOMBRE, VALOR y CUPS. Genera, juntos:

| Archivo | Contenido |
|---|---|
| `_creacion.txt` | `nombre\|PRO####\|valor\|CUPS` |
| `_carga_cups.txt` | `PRO####;valor;PRO;0;0;` (se carga como un CUPS normal) |
| `_asignacion.csv` | código que recibió cada solicitud y su estado |
| `_hallazgos.csv` | correcciones, advertencias y bloqueos |

- El consecutivo sigue el orden (después de `PRO5715`, `PRO5716`). Las
  solicitudes bloqueadas no consumen número.
- El último PRO usado hay que indicarlo: Máximos y Mínimos llega solo a
  PRO4899 (2024). La salida imprime el último código asignado.
- El nombre pasa por el mismo saneador (tildes y Ñ a letras normales,
  ASCII); `|` se reemplaza por `-` y queda registrado como corrección.
- Los archivos no terminan en salto de línea.
- Opcional: `--referencias CARPETA` avisa si el CUPS no está en el homologador.

## Conciliación con GEMANET

Compara UN anexo (un prestador, un contrato) con el reporte exportado de
GEMANET del mismo tipo. Descarta lo que ya está cargado y arma el TXT solo
con lo que falta y es válido, en vez de subir todo y recibir "ya existe en
este tarifario" o de eliminar los registros con error y dejar huecos.

En la aplicación: menú **Conciliación GEMANET** (sube el anexo y el
reporte, descarga el TXT y los informes en Excel). Desde la terminal:

```bash
python -m src.app.application.cli_conciliar anexo.xlsx --tipo CUPS \
    --gemanet GEMA_CUPS.xlsx --referencias CARPETA_REFS --salida salidas/
```

`--tipo` es `CUPS`, `CUMS` o `INS`; `--gemanet` es el reporte de ese tipo.
Procesa todas las hojas del anexo que corresponden al tipo (el resultado
dice cuáles usó y cuáles omitió; `--hojas "A,B"` para forzarlas). Con
`--solo-informes` no se escribe el TXT. Genera:

| Archivo | Contenido |
|---|---|
| `_para_cargar.txt` | **El que se sube**: solo lo que falta en GEMANET y es válido. Antes de escribirlo se verifica leyéndolo: ninguna línea repite un código ni trae uno que ya esté en GEMANET; si falla, no se escribe |
| `_faltantes.csv` | Lo que no está en GEMANET: `LISTO PARA CARGAR` (con la línea que tendría) o `CON ERROR` (con el motivo) |
| `_diferencias.csv` | Cargado con otro valor, tipo, manual o porcentaje |
| `_solo_en_gemanet.csv` | Está en GEMANET y el anexo no lo trae |
| `_inconsistencias.csv` | **Aparte**: códigos repetidos en el anexo (con valores, códigos internos y ubicación) y anomalías del reporte de GEMANET |
| `_resumen.csv` | Conteos y hojas usadas |

Reglas de la comparación:

- La clave es el código. Los CUPS del reporte vienen como número
  (`898015.0`): se normalizan y se completan a 6 dígitos.
- Un código repetido en el anexo **no se decide**: va a inconsistencias y,
  si no está en GEMANET, a faltantes con error.
- Tarifa propia contra propia: se compara el valor. Regulada contra
  regulada: el valor lo calcula GEMANET desde el manual, así que se
  comparan el manual y el porcentaje. Un tipo de tarifario vacío en el
  reporte significa regulado.
- Cada tipo de error de GEMANET tiene su validación previa: "no se
  encontró el CUPS" (formato y homologador), "ya existe en este tarifario"
  (la conciliación), "valor regulado menor" y "no se encontró el
  medicamento" (Circular 022 y Listado CUM: pendientes de implementar).

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
