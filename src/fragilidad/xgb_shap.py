"""XGBoost y valores SHAP del desenlace compuesto a 90 días, con variables de M3."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from sklearn.model_selection import StratifiedKFold
from xgboost import XGBClassifier

from fragilidad.modelos import (
    M0,
    M3,
    N_BOOT,
    N_FOLDS,
    SEMILLA,
    calibracion,
    graficar_calibracion,
    graficar_roc,
    ic_bootstrap,
    predicciones_oof,
    texto_ic,
)
from fragilidad.univariado import preparar_tiempos_compuesto

# Hiperparámetros fijos. Árboles poco profundos para no sobreajustar.
PARAMETROS_XGB = dict(
    n_estimators=300,
    max_depth=3,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=5,
    reg_lambda=1.0,
    objective="binary:logistic",
    eval_metric="auc",
    tree_method="hist",
    n_jobs=1,
    random_state=SEMILLA,
    missing=np.nan,
    verbosity=0,
)


def ajustar_xgb(X, y, params=None):
    """Ajusta un XGBClassifier. X puede tener NaN: XGBoost los maneja de forma nativa."""
    modelo = XGBClassifier(**(params or PARAMETROS_XGB))
    modelo.fit(X, y)
    return modelo


def predicciones_oof_xgb(X, y, folds, params=None):
    """Probabilidades fuera de pliegue: cada modelo se ajusta solo con el entrenamiento."""
    pred = np.full(len(y), np.nan)
    yv = y.to_numpy() if hasattr(y, "to_numpy") else np.asarray(y)
    for tr, te in folds:
        modelo = ajustar_xgb(X.iloc[tr], yv[tr], params)
        pred[te] = modelo.predict_proba(X.iloc[te])[:, 1]
    return pred


def valores_shap(modelo, X):
    """TreeExplainer: valores SHAP (log-odds) y valor base por fila."""
    explainer = shap.TreeExplainer(modelo)
    exp = explainer(X)
    valores = np.asarray(exp.values)
    base = np.asarray(exp.base_values).reshape(-1)
    if len(base) == 1:
        base = np.full(len(X), float(base[0]))
    return explainer, exp, valores, base


def margen_predicho(modelo, X):
    return np.asarray(modelo.predict(X, output_margin=True))


def direccion_hfrs(X, valores):
    """Correlación entre el HFRS y su valor SHAP (positiva = más riesgo predicho)."""
    if "hfrs" not in X.columns:
        return None
    j = list(X.columns).index("hfrs")
    x, s = X["hfrs"].to_numpy(dtype=float), valores[:, j]
    ok = np.isfinite(x) & np.isfinite(s)
    if ok.sum() < 3 or np.unique(x[ok]).size < 2 or np.std(s[ok]) == 0:
        return None
    corr = float(np.corrcoef(x[ok], s[ok])[0, 1])
    if not np.isfinite(corr):
        return None
    return {"corr": corr, "shap_medio": float(s[ok].mean()), "n": int(ok.sum())}


def _guardar(ruta):
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(ruta, dpi=150, bbox_inches="tight")
    plt.close()


def graficar_shap(exp, valores, X, i_paciente, p_paciente, n, ruta_abeja, ruta_barra, ruta_paciente):
    """Beeswarm, barras de |SHAP| medio y waterfall del paciente de ejemplo (sin identificadores)."""
    shap.plots.beeswarm(exp, max_display=20, show=False)
    plt.title("Valores SHAP (log-odds del compuesto)")
    _guardar(ruta_abeja)

    shap.plots.bar(exp, max_display=20, show=False)
    plt.title("Importancia: media del valor absoluto SHAP")
    _guardar(ruta_barra)

    shap.plots.waterfall(exp[i_paciente], show=False)
    plt.title(
        f"Persona con la probabilidad predicha más alta "
        f"(rango 1 de {n:,}; p̂ = {p_paciente:.2f}). Sin identificadores."
    )
    _guardar(ruta_paciente)
    plt.close("all")


def construir_informe(n, eventos, prevalencia, metricas, metricas_vs_m3, predichos, y, dir_hfrs, p_paciente):
    lineas = [
        "# XGBoost y valores SHAP del compuesto a 90 días",
        "",
        "El XGBoost usa las mismas 37 variables de M3 y los mismos 5 pliegues "
        f"estratificados (semilla {SEMILLA}) que la logística, en las {n:,} personas "
        f"con `seguimiento_completo` ({eventos:,} eventos, prevalencia {100 * prevalencia:.1f} %). "
        "A diferencia de la logística, no se imputan los faltantes: XGBoost los maneja "
        "de forma nativa al enviar cada valor faltante a una dirección de división "
        "aprendida. Tampoco se estandariza.",
        "",
        "Hiperparámetros fijos (sin búsqueda): "
        + ", ".join(
            f"`{k}={v}`"
            for k, v in PARAMETROS_XGB.items()
            if k not in {"objective", "eval_metric", "tree_method", "n_jobs", "verbosity", "missing"}
        )
        + ", `tree_method=hist`, `n_jobs=1`.",
        "",
        "Las predicciones de discriminación son fuera de pliegue. El AUROC, la AUPRC "
        f"y las diferencias frente a M0 y a la logística M3 llevan IC 95 % bootstrap "
        f"percentil ({N_BOOT} réplicas, semilla {SEMILLA}, comparaciones pareadas).",
        "",
        "![Curvas ROC](../figuras/roc_xgb.png)",
        "",
        "![Calibración](../figuras/calibracion_xgb.png)",
        "",
        "## Discriminación",
        "",
        "| Modelo | AUROC [IC 95%] | AUPRC [IC 95%] | ΔAUROC vs M0 [IC 95%] | ΔAUROC vs M3 [IC 95%] |",
        "|---|---|---|---|---|",
    ]
    for nombre in predichos:
        m = metricas[nombre]
        d0 = "—" if m["delta"] is None else texto_ic(m["delta"])
        if nombre in ("M0", "M3"):
            d3 = "—"
        else:
            d3m = metricas_vs_m3[nombre]["delta"]
            d3 = "—" if d3m is None else texto_ic(d3m)
        lineas.append(
            f"| {nombre} | {texto_ic(m['auroc'])} | {texto_ic(m['auprc'])} | {d0} | {d3} |"
        )
    lineas += [
        "",
        f"La AUPRC de un clasificador nulo (prevalencia) sería {prevalencia:.3f}.",
        "",
        "## Calibración fuera de pliegue",
        "",
        "| Modelo | Pendiente | Calibración-en-lo-grande (obs − pred) |",
        "|---|---:|---:|",
    ]
    for nombre, p in predichos.items():
        cal = calibracion(y, p)
        lineas.append(f"| {nombre} | {cal['pendiente']:.2f} | {cal['citl']:+.3f} |")
    lineas += [
        "",
        "## Valores SHAP",
        "",
        "El modelo de SHAP se ajusta con todas las personas de seguimiento completo "
        "(no es el modelo fuera de pliegue). Los valores explican el margen "
        "(log-odds), no la probabilidad. Las figuras no muestran `person_id` ni "
        "ningún otro identificador: el ejemplo individual es la persona con la "
        f"probabilidad predicha más alta (rango 1 de {n:,}; p̂ = {p_paciente:.2f}).",
        "",
        "![Beeswarm](../figuras/shap_beeswarm.png)",
        "",
        "![Importancia](../figuras/shap_importancia.png)",
        "",
        "![Explicación individual](../figuras/shap_paciente.png)",
        "",
        "### Dirección del HFRS",
        "",
    ]
    if dir_hfrs is None:
        lineas.append(
            "En esta muestra el HFRS no tiene variación suficiente para describir "
            "la dirección de su efecto SHAP."
        )
    else:
        signo = "positivos" if dir_hfrs["corr"] > 0 else "negativos"
        efecto = (
            "aumenta el log-odds del compuesto (más riesgo predicho)"
            if dir_hfrs["corr"] > 0
            else "disminuye el log-odds del compuesto (menos riesgo predicho)"
        )
        lineas.append(
            f"La correlación entre el HFRS y su valor SHAP es {dir_hfrs['corr']:.2f} "
            f"(n = {dir_hfrs['n']:,}). Un HFRS más alto se asocia con valores SHAP "
            f"{signo}: {efecto}. Eso es coherente con el HR univariado y con el HR "
            "ajustado del Cox de M3 si ambos apuntan en la misma dirección."
        )
    lineas += [
        "",
        "## Limitaciones",
        "",
        "- Los hiperparámetros son fijos; no hay búsqueda interna.",
        "- El SHAP describe un modelo ajustado con toda la muestra de análisis, "
        "no las predicciones fuera de pliegue.",
        "- Los pliegues son aleatorios estratificados, no un corte temporal.",
        "- XGBoost no imputa, pero la dirección en la que envía un faltante es "
        "una regla del árbol, no un modelo explícito de no respuesta.",
        "- Las figuras de SHAP muestran como máximo 20 variables.",
        "",
    ]
    return "\n".join(lineas)


def analizar(features, desenlaces):
    """Une los CSV, calcula OOF de M0, M3 y XGBoost, ajusta SHAP y devuelve el Markdown."""
    df = features.merge(desenlaces, on="person_id")
    df = preparar_tiempos_compuesto(df)
    logist = df.loc[df["seguimiento_completo"] == 1].copy()
    y = logist["compuesto"]
    X = logist[M3]
    folds = list(
        StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEMILLA).split(logist, y)
    )
    predichos = {
        "M0": predicciones_oof(logist, y, M0, folds),
        "M3": predicciones_oof(logist, y, M3, folds),
        "XGBoost": predicciones_oof_xgb(X, y, folds),
    }
    metricas = ic_bootstrap(y, predichos, referencia="M0")
    metricas_vs_m3 = ic_bootstrap(y, predichos, referencia="M3")
    graficar_roc(y, predichos, "figuras/roc_xgb.png")
    graficar_calibracion(y, predichos, "figuras/calibracion_xgb.png")

    X_shap = X.reset_index(drop=True)
    modelo = ajustar_xgb(X_shap, y.to_numpy())
    p_final = modelo.predict_proba(X_shap)[:, 1]
    i_paciente = int(np.argmax(p_final))
    _, exp, valores, _ = valores_shap(modelo, X_shap)
    graficar_shap(
        exp,
        valores,
        X_shap,
        i_paciente,
        float(p_final[i_paciente]),
        len(X_shap),
        "figuras/shap_beeswarm.png",
        "figuras/shap_importancia.png",
        "figuras/shap_paciente.png",
    )
    return construir_informe(
        n=len(logist),
        eventos=int(y.sum()),
        prevalencia=float(y.mean()),
        metricas=metricas,
        metricas_vs_m3=metricas_vs_m3,
        predichos=predichos,
        y=y,
        dir_hfrs=direccion_hfrs(X_shap, valores),
        p_paciente=float(p_final[i_paciente]),
    )


if __name__ == "__main__":
    features = pd.read_csv("data/features_cohorte.csv")
    desenlaces = pd.read_csv("data/desenlaces_cohorte.csv")
    markdown = analizar(features, desenlaces)
    Path("docs").mkdir(exist_ok=True)
    Path("docs/xgb_shap.md").write_text(markdown, encoding="utf-8")
    print(markdown)
