"""Pruebas del análisis univariado con datos de ejemplo"""
import numpy as np
import pandas as pd
import pytest

from fragilidad.univariado import (
    cox_univariado,
    logistica_univariada,
    preparar_tiempos_compuesto,
)


def test_preparar_tiempos_compuesto():
    df = pd.DataFrame(
        {
            "dias_compuesto": [10, np.nan, np.nan, 120],
            "dias_seguimiento": [200, 40, 200, 200],
            "compuesto": [1, 0, 0, 1],
        }
    )
    r = preparar_tiempos_compuesto(df)
    # Evento a 10 días; censura a 40; censura a 90; evento después del día 90 
    assert list(r["evento"]) == [1, 0, 0, 0]
    assert list(r["tiempo"]) == [10, 40, 90, 90]


def test_logistica_or_igual_que_tabla_2x2():
    x = pd.Series([1] * 8 + [0] * 12 + [np.nan])
    y = pd.Series([1] * 6 + [0] * 2 + [1] * 3 + [0] * 9 + [1])
    r = logistica_univariada(y, x)
    assert r["n"] == 20
    assert r["eventos"] == 9
    assert r["punto"] == pytest.approx(9.0, rel=1e-8)
    assert r["ic_inf"] < 9 < r["ic_sup"]
    assert r["p"] < 0.05


def test_cox_hr_tiene_el_signo_correcto():
    tiempo = np.array([20, 30, 40, 50, 70, 80, 90, 90, 5, 8, 10, 12, 15, 20, 25, 90])
    evento = np.array([1, 1, 0, 1, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0])
    x = np.array([0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1])
    r = cox_univariado(tiempo, evento, x)
    assert r["n"] == 16
    assert r["eventos"] == 9
    assert r["punto"] > 1
    assert r["ic_inf"] > 1
    assert r["p"] < 0.05
    vacio = cox_univariado(tiempo, evento, np.zeros(16))
    assert vacio["punto"] is None
    assert vacio["n"] == 16
