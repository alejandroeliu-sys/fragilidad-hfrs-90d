"""Pruebas de riesgos competitivos con datos de ejemplo"""
import numpy as np
import pandas as pd
import pytest

from fragilidad.riesgos_competitivos import (
    cif_al_dia,
    codificar_eventos,
    incidencia_acumulada,
    prueba_gray,
)

# Dos grupos de 8 personas. Tipo: 0 censura, 1 evento, 2 muerte primero.
TIEMPO = np.array([5, 10, 10, 20, 30, 40, 90, 90, 3, 5, 8, 12, 15, 25, 60, 90])
TIPO = np.array([1, 2, 1, 0, 1, 0, 0, 0, 1, 1, 2, 1, 1, 2, 1, 0])
GRUPO = np.array(["A"] * 8 + ["B"] * 8)


def test_codificar_eventos_ejemplo():
    df = pd.DataFrame(
        {
            "dias_reingreso": [10, 30, 20, np.nan, np.nan],
            "dias_muerte": [np.nan, 15, 20, 50, np.nan],
            "dias_seguimiento": [200, 200, 200, 200, 40],
        }
    )
    r = codificar_eventos(df, "reingreso")
    assert list(r["tipo"]) == [1, 2, 1, 2, 0]
    assert list(r["tiempo"]) == [10, 15, 20, 50, 40]


def test_incidencia_acumulada_a_mano():
    a = GRUPO == "A"
    cif = incidencia_acumulada(TIEMPO[a], TIPO[a], 1)
    # Día 5: 1/8. Día 10: + (7/8)(1/7). Día 30: + (5/8)(1/4).
    assert cif_al_dia(cif, 4) == 0.0
    assert cif_al_dia(cif, 10) == pytest.approx(0.25)
    assert cif_al_dia(cif, 90) == pytest.approx(0.40625)
    assert cif_al_dia(incidencia_acumulada(TIEMPO[a], TIPO[a], 2), 90) == pytest.approx(0.125)


def test_prueba_gray_igual_que_cmprsk():
    # Valor de R: cmprsk::cuminc(TIEMPO, TIPO, GRUPO)$Tests (versión 2.2-12)
    r = prueba_gray(TIEMPO, TIPO, GRUPO)
    assert r["estadistico"] == pytest.approx(0.5871864662, rel=1e-8)
    assert r["p"] == pytest.approx(0.4435091617, rel=1e-8)
    assert r["gl"] == 1
    # Con un solo grupo.
    assert prueba_gray(TIEMPO, TIPO, ["A"] * 16) is None
