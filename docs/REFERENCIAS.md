# Consulta de referencias

Reemplaza el trabajo manual de abrir tres Excel para revisar un código.

## Configuración

Los archivos van en una carpeta, que se indica en `.streamlit/secrets.toml`:

```toml
REFERENCIAS_PATH = "referencias"
```

Se reconocen por el nombre del archivo, así que basta con que contenga:

| Fuente | El nombre debe contener |
|---|---|
| Superhomologador | `SUPERHOMOLOGADOR` |
| Circular 022 | `CIRCULAR` y `MEDICAMENTO` |
| Máximos y Mínimos | `MAXIMO` |

Si falta alguno, la pantalla lo dice y sigue funcionando con los demás.

## Qué responde

| Consulta | Muestra |
|---|---|
| Servicio (CUPS) | código ley homologado, tarifa en UVB/UVT/UVR con su puntaje, simulación de descuento y rango histórico |
| Medicamento (CUM) | precio regulado por unidad, margen IPS, costo total y rango histórico |
| Insumo | rango histórico (los insumos nunca son regulados) |

También hay búsqueda por descripción para servicios y medicamentos, útil
cuando no se tiene el código. Los insumos no tienen una fuente con
descripciones, así que solo se consultan por código.

## Rendimiento

Entre los tres archivos hay más de 300.000 filas y la primera lectura
tarda cerca de 30 segundos. Después queda una copia en
`.cache_referencias/` junto a los archivos y la carga baja a unos 3
segundos. La caché se invalida sola cuando cambia el archivo original o
cuando cambia la forma de leerlo (`VERSION_CACHE`).

Los originales no se modifican. Si la carpeta es de solo lectura, se
trabaja sin caché: más lento, pero funciona.

## Advertencias que la pantalla muestra

- **Máximos y Mínimos** llega hasta la vigencia 2024 y tiene datos sucios
  (hay mínimos de dos pesos). Sirve como alerta, no como regla.
- **La Circular 022** trae una hoja de precio por unidad que es derivada:
  hay que verificar kits, combos y multidosis contra el texto oficial.
- **Un CUPS puede tener más de un código ley.** De 7.187 CUPS del
  homologador, 1.162 son ambiguos. En esos casos la pantalla avisa y no
  elige por ti.
