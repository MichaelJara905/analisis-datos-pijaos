# Consulta de documentos

Menú **Consulta de documentos**: una pestaña por documento de referencia,
cada una con su propia búsqueda. Reemplaza abrir los Excel a mano.

## Configuración

Los cuatro archivos van en una carpeta, indicada en `.streamlit/secrets.toml`
(`REFERENCIAS_PATH`) o escrita en la pantalla. Se reconocen por el nombre:

| Documento | El nombre debe contener |
|---|---|
| Circular 022 | `PRECIOS`, `UNIDAD` y `CIRCULAR` (versión nueva); si no, `CIRCULAR` y `MEDICAMENTO` (versión anterior) |
| Trazabilidad 2706 | `TRAZABILIDAD` |
| Listado CUM (INVIMA) | `LISTADO` y `UNICO` |
| SuperHomologador | `SUPERHOMOLOGADOR` |

Si la carpeta tiene las dos Circulares, se usa la nueva. Cada pestaña lee
solo su archivo, la primera vez que se abre. Si el archivo cambia, se vuelve
a leer solo; el botón **Actualizar** fuerza la lectura. Los originales no se
modifican.

La caché se guarda en `.cache_referencias/` dentro del proyecto, no junto a
los originales (que suelen estar en el Drive). Primera lectura medida con
los archivos reales: Listado CUM ~40 s, Circular ~12 s, el resto de 2 a 4 s.

## Qué responde cada pestaña

**Circular 022** (busca por CUM o por nombre)
- **Tope a parametrizar** por unidad: columna amarilla del libro =
  (PMV de la presentación + margen IPS) ÷ unidades por presentación.
- PMV por unidad, margen, % de margen aplicado, criterio, fundamento,
  circular de origen, vigencia y alerta de revisión.
- *Verificar un valor*: dice si lo ofrecido supera el tope. Los porcentajes
  son "hasta": un valor menor es válido.
- Es un libro de apoyo derivado de la Circular 022 de 2026; no sustituye el
  texto oficial.

**Trazabilidad 2706** (busca por código nuevo o anterior, o por descripción)
- **Vigente 2026**: se puede autorizar y parametrizar.
- **No vigente**: el código ya no existe; muestra el reemplazo (si lo hay) y
  el significado del tipo de trazabilidad.
- **No está en la Resolución 2706**: no se puede autorizar ni parametrizar.
- Los CUPS con el cero inicial perdido (`53109`) se completan a 6 dígitos.

**Listado CUM** (busca por CUM, expediente, producto, principio activo, titular o ATC)
- **Activo / Inactivo / No está en el listado** (sin registro = inactivo).
- Registro sanitario, fechas, forma, vía, concentración, ATC y titular.
- Alerta si la fecha de vencimiento del registro ya pasó.
- Otras presentaciones del mismo expediente.
- El libro repite cada CUM por rol del titular: aquí aparece una sola vez.

**SuperHomologador** (busca por CUPS, código SOAT o descripción)
- Homólogos SOAT del CUPS (avisa si hay más de uno; no elige).
- Valor en UVB, UVT y UVR **sin el descuento que la hoja traiga
  incorporado**, con un campo para simular el descuento pactado, y el valor
  que muestra la hoja aparte.

## Supuestos (confirmar o corregir)

- La Circular nueva reemplaza a la anterior.
- Un CUM está **activo** si figura en el Listado con ESTADO CUM = Activo.
- El valor que se contrata en medicamentos es **por unidad (UMD)**, como la
  columna del tope.
- Los archivos se leen desde una carpeta, no se suben cada vez.

## Pendiente

Usar estos mismos datos como validaciones en los cargues y en la
conciliación: CUM inactivo o ausente, CUPS fuera de la 2706 y valor por
encima del tope de la Circular. Corresponden a los errores de GEMANET
"no se encontró el medicamento / CUPS" y "valor regulado menor".
