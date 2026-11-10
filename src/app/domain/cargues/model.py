"""Estructuras de datos del cargue.

Un `Registro` es una fila del anexo con su trazabilidad completa: de dónde
salió, qué se le cambió y qué problemas tiene.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severidad(str, Enum):
    """Qué tan grave es un hallazgo."""

    BLOQUEANTE = "BLOQUEANTE"      # el registro no puede ir al TXT
    ADVERTENCIA = "ADVERTENCIA"    # va al TXT, pero hay que revisarlo
    CORRECCION = "CORRECCION"      # se corrigió automáticamente


@dataclass(frozen=True)
class Hallazgo:
    """Algo que el sistema encontró en un registro.

    Se guarda todo lo necesario para auditar después: qué campo, qué valor
    venía, qué regla se aplicó y qué se puede hacer al respecto.
    """

    fila: int
    campo: str
    severidad: Severidad
    problema: str
    valor_original: str = ""
    valor_final: str = ""
    regla: str = ""
    sugerencia: str = ""

    def como_dict(self) -> dict[str, str | int]:
        return {
            "fila": self.fila,
            "campo": self.campo,
            "severidad": self.severidad.value,
            "problema": self.problema,
            "valor_original": self.valor_original,
            "valor_final": self.valor_final,
            "regla": self.regla,
            "sugerencia": self.sugerencia,
        }


@dataclass
class Registro:
    """Una fila del anexo, ya leída y en proceso de transformación."""

    fila: int
    codigo: str = ""
    descripcion: str = ""
    descripcion_original: str = ""
    valor: int | None = None
    valor_original: str = ""
    tipo_tarifa: str = ""
    codigo_ley: str = ""
    porcentaje: int = 0
    porcentaje_norma: str = "0"
    hallazgos: list[Hallazgo] = field(default_factory=list)
    crudo: dict[str, object] = field(default_factory=dict)
    hoja: str = ""

    # --------------------------------------------------------

    def agregar(self, hallazgo: Hallazgo) -> None:
        self.hallazgos.append(hallazgo)

    @property
    def bloqueado(self) -> bool:
        return any(
            h.severidad is Severidad.BLOQUEANTE
            for h in self.hallazgos
        )

    @property
    def tiene_advertencias(self) -> bool:
        return any(
            h.severidad is Severidad.ADVERTENCIA
            for h in self.hallazgos
        )

    @property
    def es_regulado(self) -> bool:
        return self.tipo_tarifa != "" and self.tipo_tarifa != "PRO"


@dataclass
class ResultadoCargue:
    """Salida completa del proceso, lista para mostrar o exportar."""

    tipo_cargue: str
    archivo_origen: str
    hoja: str
    fila_encabezado: int
    mapeo_columnas: dict[str, str]
    registros: list[Registro]
    hallazgos_generales: list[Hallazgo] = field(default_factory=list)

    # --------------------------------------------------------

    @property
    def listos(self) -> list[Registro]:
        """Registros que pueden ir al TXT."""

        return [r for r in self.registros if not r.bloqueado]

    @property
    def bloqueados(self) -> list[Registro]:
        return [r for r in self.registros if r.bloqueado]

    @property
    def hallazgos(self) -> list[Hallazgo]:
        """Todos los hallazgos, ordenados por fila."""

        todos = list(self.hallazgos_generales)
        for registro in self.registros:
            todos.extend(registro.hallazgos)
        return sorted(todos, key=lambda h: (h.fila, h.campo))

    def resumen(self) -> dict[str, int]:
        hallazgos = self.hallazgos
        return {
            "registros_leidos": len(self.registros),
            "listos_para_cargue": len(self.listos),
            "bloqueados": len(self.bloqueados),
            "con_advertencia": sum(
                1 for r in self.registros if r.tiene_advertencias
            ),
            "correcciones": sum(
                1 for h in hallazgos if h.severidad is Severidad.CORRECCION
            ),
            "advertencias": sum(
                1 for h in hallazgos if h.severidad is Severidad.ADVERTENCIA
            ),
            "bloqueantes": sum(
                1 for h in hallazgos if h.severidad is Severidad.BLOQUEANTE
            ),
        }
