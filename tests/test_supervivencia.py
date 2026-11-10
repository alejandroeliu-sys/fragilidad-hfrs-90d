"""Pruebas de las funciones de supervivencia, con datos de ejemplo."""
import numpy as np
import pandas as pd

from fragilidad.supervivencia import asignar_terciles, preparar_tiempos


def test_preparar_tiempos_muerte_y_censura_a_90_ejemplo():
    # Datos de ejemplo.
    df = pd.DataFrame(
        {
            "dias_muerte": [10, np.nan, np.nan, 45],
            "dias_seguimiento": [90, 90, 120, 90],
            "muerte": [1, 0, 0, 1],
        }
    )
    r = preparar_tiempos(df)
    assert list(r["evento"]) == [1, 0, 0, 1]
    assert list(r["tiempo"]) == [10, 90, 90, 45]


def test_preparar_tiempos_seguimiento_incompleto_ejemplo():
    # Persona de ejemplo 
    df = pd.DataFrame(
        {
            "dias_muerte": [np.nan],
            "dias_seguimiento": [40],
            "muerte": [0],
        }
    )
    r = preparar_tiempos(df)
    assert int(r["evento"].iloc[0]) == 0
    assert int(r["tiempo"].iloc[0]) == 40


def test_asignar_terciles_con_empates_ejemplo():
    hfrs = pd.Series([0.6] * 10 + [0.0] * 2 + [5.0] * 2)
    etiquetas, cortes, n_grupos = asignar_terciles(hfrs)
    assert 1 <= n_grupos <= 3
    assert len(cortes) == n_grupos + 1
    assert set(etiquetas.dropna().astype(str)) <= {"T1", "T2", "T3"}

    iguales = pd.Series([0.6] * 12)
    etiquetas2, _, n2 = asignar_terciles(iguales)
    assert n2 == 1
    assert list(etiquetas2.unique()) == ["T1"]
