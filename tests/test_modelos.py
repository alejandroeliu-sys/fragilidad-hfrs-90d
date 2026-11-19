"""Pruebas de los modelos anidados con datos de ejemplo"""
import numpy as np
import pandas as pd
import pytest

from fragilidad.modelos import (
    EXCLUIDAS_FALTA,
    MODELOS,
    ajustar_imputacion,
    aplicar_imputacion,
    auroc,
    ic_bootstrap,
)


def test_modelos_anidados_y_exclusiones():
    assert MODELOS["M0"] == ["hfrs"]
    assert set(MODELOS["M0"]) <= set(MODELOS["M1"]) <= set(MODELOS["M2"]) <= set(MODELOS["M3"])
    assert "edad" in MODELOS["M1"] and "sexo_masc" in MODELOS["M1"]
    assert "demencia_dx" in MODELOS["M2"] and "n_ingredientes_30" in MODELOS["M2"]
    assert "estancia_indice_dias" in MODELOS["M3"] and "pas_falta" in MODELOS["M3"]
    for col in ("albumina_ultima", "creatinina_ultima", "tfge_ultima"):
        assert col in MODELOS["M3"]
    for flag in EXCLUIDAS_FALTA:
        assert flag not in MODELOS["M3"]
    assert "obs_previa_dias" not in MODELOS["M3"]


def test_imputacion_mediana_solo_entrenamiento():
    train = pd.DataFrame(
        {"a": [1.0, 3.0, np.nan], "b": [0, 0, 0], "c": [np.nan, np.nan, np.nan]}
    )
    test = pd.DataFrame({"a": [np.nan, 10.0], "b": [1, 0], "c": [5.0, 6.0]})
    usables, medianas = ajustar_imputacion(train, ["a", "b", "c"])
    assert usables == ["a"]
    assert medianas["a"] == 2.0
    xte = aplicar_imputacion(test, usables, medianas)
    assert list(xte["a"]) == [2.0, 10.0]


def test_auroc_perfecto_y_delta_bootstrap():
    y = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    p0 = np.array([0.4, 0.45, 0.5, 0.55, 0.5, 0.55, 0.6, 0.65])
    p1 = np.array([0.1, 0.2, 0.2, 0.3, 0.7, 0.8, 0.8, 0.9])
    assert auroc(y, p1) == pytest.approx(1.0)
    r = ic_bootstrap(y, {"M0": p0, "M1": p1}, n_boot=200, semilla=0)
    assert r["M1"]["auroc"]["punto"] == pytest.approx(1.0)
    assert r["M0"]["auroc"]["inf"] <= r["M0"]["auroc"]["punto"] <= r["M0"]["auroc"]["sup"]
    assert r["M1"]["delta"]["punto"] > 0
    assert r["M1"]["delta"]["inf"] >= 0
