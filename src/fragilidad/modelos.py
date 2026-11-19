"""Modelos anidados M0-M3 del desenlace compuesto a 90 días."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from lifelines import CoxPHFitter
from lifelines.statistics import proportional_hazard_test
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve
from sklearn.model_selection import StratifiedKFold

from fragilidad.tabla1 import formatear_p
from fragilidad.univariado import preparar_tiempos_compuesto, texto_efecto

SEMILLA = 42
N_FOLDS = 5
N_BOOT = 1000
# C=np.inf = logística sin penalización.
LOGISTICA = dict(C=np.inf, solver="lbfgs", max_iter=2000)
PENALIZADORES_COX = (0.0, 0.01, 0.1)

# albumina_falta, creatinina_falta y tfge_falta son inestables segun el univariado, por lo cual se excluyen.
EXCLUIDAS_FALTA = ("albumina_falta", "creatinina_falta", "tfge_falta")

M0 = ["hfrs"]
M1 = M0 + ["edad", "sexo_masc"]
M2 = M1 + [
    "dm2_dx", "ic_dx", "erc_dx", "demencia_dx", "cardiop_isq_dx", "hta_dx", "anemia_dx",
    "n_ingredientes_365", "n_ingredientes_30", "dm_inferida", "hta_inferida", "ic_inferida",
]
M3 = M2 + [
    "albumina_ultima", "albumina_n", "albumina_pendiente", "albumina_de",
    "creatinina_ultima", "creatinina_n", "creatinina_pendiente",
    "urea_ultima", "urea_n", "urea_pendiente",
    "hemoglobina_ultima", "tfge_ultima", "pas_ultima", "imc_ultimo",
    "n_ambulatorias_365", "n_hosp_365", "n_urgencias_365", "estancia_indice_dias",
    "urea_falta", "hemoglobina_falta", "pas_falta", "imc_falta",
]
MODELOS = {"M0": M0, "M1": M1, "M2": M2, "M3": M3}


def ajustar_imputacion(train, columnas):
    """Medianas del entrenamiento y columnas con variación tras imputar.

    Se descarta una columna si en el entrenamiento está toda vacía o queda
    constante después de llenar los huecos con la mediana.
    """
    usables, medianas = [], {}
    for c in columnas:
        if c not in train.columns or train[c].notna().sum() == 0:
            continue
        med = train[c].median()
        if pd.isna(med):
            continue
        if train[c].fillna(med).nunique() < 2:
            continue
        usables.append(c)
        medianas[c] = float(med)
    return usables, medianas


def aplicar_imputacion(df, usables, medianas):
    return pd.DataFrame({c: df[c].fillna(medianas[c]) for c in usables}, index=df.index)


def sin_duplicadas(df):
    """Deja la primera de dos columnas idénticas (evita una matriz singular)."""
    keep, vistos = [], []
    for c in df.columns:
        col = df[c].to_numpy()
        if any(np.array_equal(col, v) for v in vistos):
            continue
        keep.append(c)
        vistos.append(col)
    return keep


def preparar_matriz(train, test, columnas):
    """Imputa con medianas del train, quita constantes y columnas duplicadas."""
    usables, medianas = ajustar_imputacion(train, columnas)
    if not usables:
        return usables, None, None
    xtr = aplicar_imputacion(train, usables, medianas)
    xte = aplicar_imputacion(test, usables, medianas)
    keep = sin_duplicadas(xtr)
    return keep, xtr[keep], xte[keep]


def estandarizar(xtr, xte):
    """Media y DE del entrenamiento (la logística unpenalizada es equivalente, pero lbfgs converge)."""
    media = xtr.mean(axis=0)
    de = xtr.std(axis=0, ddof=0).replace(0, 1)
    return (xtr - media) / de, (xte - media) / de


def auroc(y, p):
    return float(roc_auc_score(y, p))


def auprc(y, p):
    return float(average_precision_score(y, p))


def predicciones_oof(X, y, columnas, folds):
    """Probabilidades fuera de pliegue; si no hay predictores útiles, usa la prevalencia del train."""
    pred = np.full(len(y), np.nan)
    yv = y.to_numpy() if hasattr(y, "to_numpy") else np.asarray(y)
    for tr, te in folds:
        keep, xtr, xte = preparar_matriz(X.iloc[tr], X.iloc[te], columnas)
        if not keep:
            pred[te] = yv[tr].mean()
            continue
        xtr, xte = estandarizar(xtr, xte)
        modelo = LogisticRegression(**LOGISTICA)
        modelo.fit(xtr.to_numpy(), yv[tr])
        pred[te] = modelo.predict_proba(xte.to_numpy())[:, 1]
    return pred


def ic_bootstrap(y, predichos, n_boot=N_BOOT, semilla=SEMILLA):
    """AUROC, AUPRC y ΔAUROC frente a M0, con IC 95 % percentil (mismas réplicas)."""
    rng = np.random.default_rng(semilla)
    y = np.asarray(y)
    n = len(y)
    nombres = list(predichos)
    arrays = {k: np.asarray(predichos[k]) for k in nombres}
    boots = {k: {"auroc": [], "auprc": []} for k in nombres}
    deltas = {k: [] for k in nombres if k != "M0"}
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        ys = y[idx]
        if ys.min() == ys.max():
            continue
        aucs = {}
        for k in nombres:
            ps = arrays[k][idx]
            aucs[k] = auroc(ys, ps)
            boots[k]["auroc"].append(aucs[k])
            boots[k]["auprc"].append(auprc(ys, ps))
        for k in deltas:
            deltas[k].append(aucs[k] - aucs["M0"])

    def punto_ic(valores, observado):
        xs = np.asarray(valores)
        return {
            "punto": float(observado),
            "inf": float(np.quantile(xs, 0.025)),
            "sup": float(np.quantile(xs, 0.975)),
        }

    out = {}
    for k in nombres:
        out[k] = {
            "auroc": punto_ic(boots[k]["auroc"], auroc(y, arrays[k])),
            "auprc": punto_ic(boots[k]["auprc"], auprc(y, arrays[k])),
            "delta": None if k == "M0" else punto_ic(deltas[k], auroc(y, arrays[k]) - auroc(y, arrays["M0"])),
        }
    return out


def calibracion(y, p, n_grupos=10):
    """Deciles OOF, pendiente de recálculo y calibración-en-lo-grande (obs − pred)."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    grupos = pd.qcut(p, n_grupos, duplicates="drop")
    tab = pd.DataFrame({"y": y, "p": p, "g": grupos}).groupby("g", observed=True).mean()
    p_clip = np.clip(p, 1e-6, 1 - 1e-6)
    logit = np.log(p_clip / (1 - p_clip)).reshape(-1, 1)
    rec = LogisticRegression(**LOGISTICA)
    rec.fit(logit, y)
    return {
        "predicho": tab["p"].to_numpy(),
        "observado": tab["y"].to_numpy(),
        "pendiente": float(rec.coef_[0, 0]),
        "citl": float(y.mean() - p.mean()),
    }


def texto_ic(res, dec=3):
    return f"{res['punto']:.{dec}f} [{res['inf']:.{dec}f}-{res['sup']:.{dec}f}]"


def graficar_roc(y, predichos, ruta):
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 7))
    for nombre, p in predichos.items():
        fpr, tpr, _ = roc_curve(y, p)
        ax.plot(fpr, tpr, label=f"{nombre} (AUROC {auroc(y, p):.3f})")
    ax.plot([0, 1], [0, 1], ls="--", color="0.5", lw=0.8)
    ax.set(xlabel="1 − especificidad", ylabel="Sensibilidad",
           title="Curvas ROC fuera de pliegue (compuesto a 90 días)",
           xlim=(0, 1), ylim=(0, 1))
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def graficar_calibracion(y, predichos, ruta):
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 7))
    for nombre, p in predichos.items():
        cal = calibracion(y, p)
        ax.plot(cal["predicho"], cal["observado"], "o-", label=nombre)
    ax.plot([0, 1], [0, 1], ls="--", color="0.5", lw=0.8)
    ax.set(xlabel="Probabilidad predicha (media del decil)",
           ylabel="Fracción observada",
           title="Calibración fuera de pliegue (deciles)",
           xlim=(0, 1), ylim=(0, 1))
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def ajustar_cox(df, columnas):
    """Cox de M3 en la muestra con tiempo > 0. Prueba penalizer 0, 0.01 y 0.1."""
    base = df.loc[df["tiempo"] > 0].copy()
    keep, x, _ = preparar_matriz(base, base, columnas)
    datos = pd.concat([base[["tiempo", "evento"]], x], axis=1)
    ultimo = None
    for pen in PENALIZADORES_COX:
        try:
            modelo = CoxPHFitter(penalizer=pen)
            modelo.fit(datos, duration_col="tiempo", event_col="evento")
            res = modelo.summary
            if np.isfinite(res["exp(coef)"]).all() and np.isfinite(res["exp(coef) lower 95%"]).all():
                ph = proportional_hazard_test(modelo, datos, time_transform="rank")
                return {
                    "modelo": modelo,
                    "penalizer": pen,
                    "columnas": keep,
                    "n": int(len(datos)),
                    "eventos": int(datos["evento"].sum()),
                    "c_index": float(modelo.concordance_index_),
                    "hr": [
                        {
                            "variable": str(var),
                            "hr": float(fila["exp(coef)"]),
                            "ic_inf": float(fila["exp(coef) lower 95%"]),
                            "ic_sup": float(fila["exp(coef) upper 95%"]),
                            "p": float(fila["p"]),
                        }
                        for var, fila in res.iterrows()
                    ],
                    "ph": [
                        {
                            "variable": str(var),
                            "estadistico": float(fila["test_statistic"]),
                            "p": float(fila["p"]),
                        }
                        for var, fila in ph.summary.iterrows()
                    ],
                }
        except Exception as error:
            ultimo = error
    raise RuntimeError(f"El Cox de M3 no convergió: {ultimo}")


def construir_informe(n_log, ev_log, predichos, y, metricas, cox, prevalencia):
    lineas = [
        "# Modelos anidados del desenlace compuesto a 90 días",
        "",
        "M0 es el HFRS solo (estándar de referencia). M1 agrega edad y sexo; "
        "M2, comorbilidades, fármacos inferidos y número de ingredientes; "
        "M3, laboratorios, utilización y estancia índice. En M3 se conservan "
        "los valores de `albumina_ultima`, `creatinina_ultima`, `tfge_ultima` y "
        "el resto de laboratorios preespecificados, aunque no hayan sido "
        "significativos en el univariado; solo se excluyen los indicadores "
        "`albumina_falta`, `creatinina_falta` y `tfge_falta` por inestabilidad. "
        "Se conservan los demás `_falta`. Los huecos de los laboratorios se "
        "imputan con la mediana dentro de cada pliegue (solo con el entrenamiento).",
        "",
        "La discriminación se evalúa con logística sin penalización "
        f"(`C=np.inf`) sobre el compuesto binario, en {n_log:,} personas con "
        f"`seguimiento_completo` ({ev_log:,} eventos, prevalencia {100 * prevalencia:.1f} %). "
        f"Validación cruzada estratificada de {N_FOLDS} pliegues (semilla {SEMILLA}), "
        "con predicciones fuera de pliegue. En cada pliegue la mediana de imputación "
        "se calcula solo en el entrenamiento; se descartan columnas constantes, "
        "totalmente vacías o duplicadas exactas. En la logística se estandariza "
        "con media y DE del entrenamiento solo para que el ajuste converja "
        "(el modelo sin penalización es equivalente). El Cox de M3 no se "
        "estandariza: sus HR quedan por unidad natural (el HFRS, por punto). "
        "AUROC, AUPRC y la "
        f"diferencia de AUROC frente a M0 llevan IC 95 % bootstrap percentil ({N_BOOT} "
        "réplicas, la misma semilla; las comparaciones van pareadas).",
        "",
        "![Curvas ROC](../figuras/roc_modelos.png)",
        "",
        "![Calibración](../figuras/calibracion_modelos.png)",
        "",
        "## Discriminación",
        "",
        "| Modelo | Predictores | AUROC [IC 95%] | AUPRC [IC 95%] | ΔAUROC vs M0 [IC 95%] |",
        "|---|---:|---|---|---|",
    ]
    for nombre, cols in MODELOS.items():
        m = metricas[nombre]
        delta = "—" if m["delta"] is None else texto_ic(m["delta"])
        lineas.append(
            f"| {nombre} | {len(cols)} | {texto_ic(m['auroc'])} | "
            f"{texto_ic(m['auprc'])} | {delta} |"
        )
    lineas += [
        "",
        f"La AUPRC de un clasificador nulo (prevalencia) sería {prevalencia:.3f}.",
        "",
        "## Calibración fuera de pliegue",
        "",
        "La pendiente es el coeficiente de `logit(p)` al recalar la logística "
        "(1 = ideal). La calibración-en-lo-grande es la diferencia entre la "
        "fracción observada y la probabilidad media predicha (0 = ideal).",
        "",
        "| Modelo | Pendiente | Calibración-en-lo-grande (obs − pred) |",
        "|---|---:|---:|",
    ]
    for nombre in MODELOS:
        cal = calibracion(y, predichos[nombre])
        lineas.append(f"| {nombre} | {cal['pendiente']:.2f} | {cal['citl']:+.3f} |")

    lineas += [
        "",
        "## Cox multivariable de M3",
        "",
    ]
    if cox["penalizer"] == 0:
        pen_txt = "Sin penalización (`penalizer=0`)."
    else:
        pen_txt = (
            f"Se usó `penalizer={cox['penalizer']}` (L2) porque el ajuste sin "
            "penalización no convergió o produjo HR o intervalos no finitos. "
            "Los HR siguen estando por unidad natural."
        )
    lineas += [
        f"Personas con tiempo > 0: {cox['n']:,}; eventos: {cox['eventos']:,}. "
        f"C-index aparente (en la misma muestra, no es validación cruzada): "
        f"{cox['c_index']:.3f}. Columnas usadas tras imputar y quitar constantes "
        f"o duplicadas: {len(cox['columnas'])} de {len(M3)} especificadas."
        + (
            " Se omitieron por estar vacías, ser constantes o estar duplicadas: "
            + ", ".join(f"`{c}`" for c in M3 if c not in cox["columnas"])
            + "."
            if any(c not in cox["columnas"] for c in M3)
            else ""
        )
        + f" {pen_txt}",
        "",
        "| Variable | HR [IC 95%] | p |",
        "|---|---|---:|",
    ]
    por_var = {fila["variable"]: fila for fila in cox["hr"]}
    for col in cox["columnas"]:
        fila = por_var[col]
        lineas.append(
            f"| `{col}` | {texto_efecto(fila['hr'], fila['ic_inf'], fila['ic_sup'])} | "
            f"{formatear_p(fila['p'])} |"
        )
    lineas += [
        "",
        "`creatinina_ultima` y `tfge_ultima` entran juntas en M3. Están "
        "colineales (la TFGe se deriva de la creatinina), así que sus HR "
        "ajustados son difíciles de interpretar por separado; la predicción "
        "(AUROC, AUPRC, C-index) no se afecta por esa colinealidad. Si la "
        "función renal no se asocia con el compuesto, hay que leerlo como "
        "un artefacto de Synthea, no como un hallazgo clínico.",
        "",
        "### Riesgos proporcionales (prueba de Schoenfeld, transformación rank)",
        "",
        "| Variable | Estadístico | p |",
        "|---|---:|---:|",
    ]
    for fila in cox["ph"]:
        lineas.append(
            f"| `{fila['variable']}` | {fila['estadistico']:.2f} | {formatear_p(fila['p'])} |"
        )
    n_ph = sum(f["p"] < 0.05 for f in cox["ph"])
    lineas += [
        "",
        f"{n_ph} covariable(s) tienen p < 0.05 en la prueba de proporcionalidad; "
        "su HR se interpreta como un promedio a lo largo del seguimiento.",
        "",
        "## Limitaciones",
        "",
        "- Los pliegues son aleatorios estratificados, no un corte temporal por "
        "`fecha_indice`.",
        "- La imputación por mediana (aunque solo se ajuste en el entrenamiento) "
        "es simple; en pendientes y desviaciones hay muchos huecos porque "
        "exigen al menos tres días con medición.",
        "- El C-index del Cox es aparente (se estima y se evalúa en la misma muestra).",
        "- El Cox no se estandariza; un HR cercano a 1 por unidad natural puede "
        "seguir siendo relevante (edad por año, HFRS por punto).",
        "- M0-M3 están preespecificados; no hay selección automática de variables.",
        "- La creatinina y la TFGe son colineales: no se interprete cada HR "
        "ajustado por separado. La falta de asociación de la función renal "
        "con el compuesto es un artefacto de Synthea.",
        "",
    ]
    return "\n".join(lineas)


def analizar(features, desenlaces):
    """Une los CSV, ajusta M0-M3 y el Cox de M3, y devuelve el Markdown."""
    df = features.merge(desenlaces, on="person_id")
    df = preparar_tiempos_compuesto(df)
    logist = df.loc[df["seguimiento_completo"] == 1].copy()
    y = logist["compuesto"]
    folds = list(
        StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEMILLA).split(logist, y)
    )
    predichos = {
        nombre: predicciones_oof(logist, y, cols, folds) for nombre, cols in MODELOS.items()
    }
    metricas = ic_bootstrap(y, predichos)
    graficar_roc(y, predichos, "figuras/roc_modelos.png")
    graficar_calibracion(y, predichos, "figuras/calibracion_modelos.png")
    cox = ajustar_cox(df, M3)
    return construir_informe(
        n_log=len(logist),
        ev_log=int(y.sum()),
        predichos=predichos,
        y=y,
        metricas=metricas,
        cox=cox,
        prevalencia=float(y.mean()),
    )


if __name__ == "__main__":
    features = pd.read_csv("data/features_cohorte.csv")
    desenlaces = pd.read_csv("data/desenlaces_cohorte.csv")
    markdown = analizar(features, desenlaces)
    Path("docs").mkdir(exist_ok=True)
    Path("docs/modelos.md").write_text(markdown, encoding="utf-8")
    print(markdown)
