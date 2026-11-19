"""Pruebas de XGBoost/SHAP con datos de ejemplo"""
import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import StratifiedKFold
from xgboost import XGBClassifier

from fragilidad.modelos import ic_bootstrap
from fragilidad.xgb_shap import (
    PARAMETROS_XGB,
    ajustar_xgb,
    margen_predicho,
    predicciones_oof_xgb,
    valores_shap,
)


def _params_cortos():
    p = dict(PARAMETROS_XGB)
    p["n_estimators"] = 20
    return p


def test_shap_mas_base_igual_al_margen():
    rng = np.random.default_rng(0)
    X = pd.DataFrame(
        {
            "a": rng.normal(size=40),
            "b": rng.normal(size=40),
            "hfrs": rng.choice([0.0, 5.0, 10.0], size=40),
        }
    )
    y = (X["a"] + 0.4 * X["hfrs"] > 0).astype(int)
    modelo = ajustar_xgb(X, y, params=_params_cortos())
    _, _, valores, base = valores_shap(modelo, X)
    margen = margen_predicho(modelo, X)
    reconstruido = valores.sum(axis=1) + base
    assert reconstruido == pytest.approx(margen, abs=1e-5)


def test_oof_no_usa_fila_de_prueba(monkeypatch):
    rng = np.random.default_rng(1)
    n = 40
    X = pd.DataFrame({"a": rng.normal(size=n), "b": rng.normal(size=n)})
    y = pd.Series((X["a"] > 0).astype(int))
    folds = list(StratifiedKFold(n_splits=5, shuffle=True, random_state=0).split(X, y))
    vistos = []
    original = XGBClassifier.fit

    def fit(self, X_fit, y_fit, **kwargs):
        vistos.append(set(np.asarray(X_fit.index)))
        return original(self, X_fit, y_fit, **kwargs)

    monkeypatch.setattr(XGBClassifier, "fit", fit)
    pred = predicciones_oof_xgb(X, y, folds, params=_params_cortos())
    assert len(vistos) == len(folds)
    assert np.isfinite(pred).all()
    for (tr, te), usados in zip(folds, vistos):
        assert usados == set(X.index[tr])
        assert usados.isdisjoint(set(X.index[te]))


def test_ic_bootstrap_referencia_m3():
    y = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    p0 = np.array([0.4, 0.45, 0.5, 0.55, 0.5, 0.55, 0.6, 0.65])
    p3 = np.array([0.2, 0.3, 0.3, 0.4, 0.6, 0.7, 0.7, 0.8])
    r = ic_bootstrap(y, {"M0": p0, "M3": p3}, n_boot=200, semilla=0, referencia="M3")
    assert r["M3"]["delta"] is None
    assert r["M0"]["delta"]["punto"] < 0
