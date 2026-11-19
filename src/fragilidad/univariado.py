"""Cox y logística univariados del desenlace compuesto a 90 días."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from lifelines import CoxPHFitter
from scipy.stats import norm

from fragilidad.tabla1 import formatear_p

AUXILIARES = {"person_id", "fecha_indice"}

BLOQUES = [
    ("Demografía", ["edad", "sexo_masc", "obs_previa_dias"]),
    (
        "Comorbilidades",
        ["dm2_dx", "ic_dx", "erc_dx", "demencia_dx", "cardiop_isq_dx", "hta_dx", "anemia_dx"],
    ),
    (
        "Fármacos",
        ["n_ingredientes_365", "n_ingredientes_30", "dm_inferida", "hta_inferida", "ic_inferida"],
    ),
    (
        "Laboratorios y signos",
        [
            "albumina_ultima", "albumina_n", "albumina_pendiente", "albumina_de",
            "creatinina_ultima", "creatinina_n", "creatinina_pendiente",
            "urea_ultima", "urea_n", "urea_pendiente",
            "hemoglobina_ultima", "tfge_ultima", "pas_ultima", "imc_ultimo",
        ],
    ),
    (
        "Utilización y estancia",
        ["n_ambulatorias_365", "n_hosp_365", "n_urgencias_365", "estancia_indice_dias"],
    ),
    ("HFRS", ["hfrs"]),
    (
        "Indicadores de faltante",
        [
            "albumina_falta", "creatinina_falta", "urea_falta",
            "hemoglobina_falta", "tfge_falta", "pas_falta", "imc_falta",
        ],
    ),
]


def preparar_tiempos_compuesto(df):
    """Tiempo y evento del compuesto a 90 días.

    Si el compuesto ocurrió en el día 1 a 90, el tiempo es dias_compuesto
    y el evento vale 1. Si no, el tiempo es el mínimo entre dias_seguimiento
    y 90, y el evento vale 0 (censura).
    """
    df = df.copy()
    evento = (
        (df["compuesto"] == 1)
        & df["dias_compuesto"].notna()
        & (df["dias_compuesto"] <= 90)
    )
    df["evento"] = evento.astype(int)
    censura = np.minimum(df["dias_seguimiento"], 90)
    df["tiempo"] = np.where(evento, df["dias_compuesto"], censura)
    return df


def lista_predictores(columnas):
    """Todas las columnas salvo identificadores y fechas; el orden sigue BLOQUES."""
    conocidos = [c for _, cols in BLOQUES for c in cols if c in columnas]
    resto = [c for c in columnas if c not in AUXILIARES and c not in conocidos]
    return conocidos + resto


def _vacio(n, eventos):
    return {"n": n, "eventos": eventos, "punto": None, "ic_inf": None, "ic_sup": None, "p": None}


def cox_univariado(tiempo, evento, x):
    """Cox de un predictor (lifelines, sin penalización). Casos completos con tiempo > 0."""
    datos = pd.DataFrame({"tiempo": tiempo, "evento": evento, "x": x}).dropna()
    datos = datos.loc[datos["tiempo"] > 0]
    n, eventos = len(datos), int(datos["evento"].sum())
    if n < 2 or eventos == 0 or datos["x"].nunique() < 2:
        return _vacio(n, eventos)
    try:
        modelo = CoxPHFitter()
        modelo.fit(datos, duration_col="tiempo", event_col="evento")
        fila = modelo.summary.loc["x"]
        vals = [fila["exp(coef)"], fila["exp(coef) lower 95%"], fila["exp(coef) upper 95%"], fila["p"]]
        if not np.isfinite(vals).all():
            return _vacio(n, eventos)
        return {"n": n, "eventos": eventos, "punto": float(vals[0]),
                "ic_inf": float(vals[1]), "ic_sup": float(vals[2]), "p": float(vals[3])}
    except Exception:
        return _vacio(n, eventos)


def logistica_univariada(y, x):
    """Logística sin penalización (IRLS): intercepto + un predictor. Casos completos.

    No se agrega statsmodels ni scikit-learn: el MLE de un predictor se obtiene
    con Newton-Raphson y el error estándar de Wald sale de la información de Fisher.
    """
    datos = pd.DataFrame({"y": y, "x": x}).dropna()
    n, eventos = len(datos), int(datos["y"].sum())
    if n < 2 or eventos == 0 or eventos == n or datos["x"].nunique() < 2:
        return _vacio(n, eventos)
    X = np.column_stack([np.ones(n), datos["x"].to_numpy(dtype=float)])
    yv = datos["y"].to_numpy(dtype=float)
    beta = np.zeros(2)
    for _ in range(50):
        p = 1 / (1 + np.exp(-np.clip(X @ beta, -30, 30)))
        w = p * (1 - p)
        try:
            delta = np.linalg.solve((X.T * w) @ X, X.T @ (yv - p))
        except np.linalg.LinAlgError:
            return _vacio(n, eventos)
        beta = beta + delta
        if np.max(np.abs(delta)) < 1e-8:
            break
    else:
        return _vacio(n, eventos)
    p = 1 / (1 + np.exp(-np.clip(X @ beta, -30, 30)))
    w = p * (1 - p)
    try:
        se = np.sqrt(np.linalg.inv((X.T * w) @ X)[1, 1])
    except np.linalg.LinAlgError:
        return _vacio(n, eventos)
    if not np.isfinite(se) or se <= 0:
        return _vacio(n, eventos)
    zcrit = norm.ppf(0.975)
    log_or = beta[1]
    return {
        "n": n,
        "eventos": eventos,
        "punto": float(np.exp(log_or)),
        "ic_inf": float(np.exp(log_or - zcrit * se)),
        "ic_sup": float(np.exp(log_or + zcrit * se)),
        "p": float(2 * norm.sf(abs(log_or / se))),
    }


def ajustar_univariados(df, predictores):
    """Cox en toda la cohorte y logística solo con seguimiento_completo, por predictor."""
    completos = df.loc[df["seguimiento_completo"] == 1]
    filas = []
    for col in predictores:
        filas.append(
            {
                "variable": col,
                "cox": cox_univariado(df["tiempo"], df["evento"], df[col]),
                "logistica": logistica_univariada(completos["compuesto"], completos[col]),
            }
        )
    return filas


def texto_efecto(punto, inf, sup):
    """2 decimales, o 3-4 si el efecto por unidad queda muy cerca de 1."""
    if punto is None or not np.isfinite([punto, inf, sup]).all():
        return "—"
    holgura = max(abs(punto - 1), abs(inf - 1), abs(sup - 1))
    dec = 4 if holgura < 0.005 else 3 if holgura < 0.05 else 2
    return f"{punto:.{dec}f} [{inf:.{dec}f}-{sup:.{dec}f}]"


def _bloques_de(resultados):
    por_var = {r["variable"]: r for r in resultados}
    usados = set()
    bloques = []
    for titulo, cols in BLOQUES:
        filas = [por_var[c] for c in cols if c in por_var]
        if filas:
            bloques.append((titulo, filas))
            usados.update(r["variable"] for r in filas)
    resto = [r for r in resultados if r["variable"] not in usados]
    if resto:
        bloques.append(("Otras", resto))
    return bloques


def _linea(r):
    c, o = r["cox"], r["logistica"]
    return (
        f"| `{r['variable']}` | {c['n']:,} | {c['eventos']:,} | "
        f"{texto_efecto(c['punto'], c['ic_inf'], c['ic_sup'])} | {formatear_p(c['p']) if c['p'] is not None else '—'} | "
        f"{o['n']:,} | {o['eventos']:,} | "
        f"{texto_efecto(o['punto'], o['ic_inf'], o['ic_sup'])} | {formatear_p(o['p']) if o['p'] is not None else '—'} |"
    )


def construir_informe(df, resultados):
    """Arma el Markdown con una tabla por bloque y las limitaciones."""
    n_cox = int((df["tiempo"] > 0).sum())
    ev_cox = int(df.loc[df["tiempo"] > 0, "evento"].sum())
    log_ok = df["seguimiento_completo"] == 1
    n_sin_tiempo = int((df["tiempo"] <= 0).sum())
    n_incompleto = int((df["seguimiento_completo"] == 0).sum())
    ev_incompleto = int(((df["seguimiento_completo"] == 0) & (df["compuesto"] == 1)).sum())
    cabecera = (
        "| Variable | n Cox | Eventos | HR [IC 95%] | p | "
        "n log. | Eventos | OR [IC 95%] | p |"
    )
    sep = "|---|---:|---:|---|---:|---:|---:|---|---:|"
    lineas = [
        "# Análisis univariado del desenlace compuesto a 90 días",
        "",
        f"Personas unidas: {len(df):,}. El Cox usa el tiempo hasta el compuesto "
        "o la censura en `min(dias_seguimiento, 90)`; se excluye a quien no tiene "
        f"tiempo de observación (tiempo ≤ 0): quedan {n_cox:,} personas y "
        f"{ev_cox:,} eventos. La logística se ajusta solo en quienes tienen "
        f"`seguimiento_completo` ({int(log_ok.sum()):,} personas, "
        f"{int(df.loc[log_ok, 'compuesto'].sum()):,} eventos). Cada modelo es "
        "univariado y usa casos completos de esa variable (la n puede cambiar). "
        "Las continuas se reportan por unidad natural; el HFRS, por punto. "
        "El Cox es el de `lifelines.CoxPHFitter` (sin penalización). La logística "
        "es el MLE sin penalización (IRLS) de un intercepto y un predictor.",
        "",
        "Un guion (—) significa que no se pudo estimar: la variable era constante, "
        "estaba vacía, no hubo eventos o no eventos, o el ajuste no convergió.",
    ]
    for titulo, filas in _bloques_de(resultados):
        lineas += ["", f"## {titulo}", "", cabecera, sep] + [_linea(r) for r in filas]
    lineas += [
        "",
        "## Limitaciones",
        "",
        "- Los modelos son univariados: no hay ajuste por confusores.",
        f"- En el Cox se dejaron fuera {n_sin_tiempo} personas con tiempo ≤ 0.",
        f"- La logística no incluye a {n_incompleto} personas con seguimiento "
        f"incompleto, de las cuales {ev_incompleto} ya habían tenido el compuesto "
        "(reingreso o urgencias) antes de perderse de vista.",
        "- Los faltantes no se imputan; cada fila reporta la n de ese modelo.",
        "- Un efecto por unidad muy cercano a 1 (por ejemplo, `obs_previa_dias` "
        "por un día) puede ser significativo y aun así verse casi como 1.00.",
        "",
    ]
    return "\n".join(lineas)


def graficar_forest(resultados, ruta):
    """Forest plot de las HR univariadas que sí se pudieron estimar."""
    filas = [
        r for r in resultados
        if r["cox"]["punto"] is not None and np.isfinite(r["cox"]["punto"])
    ]
    if not filas:
        return
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, max(4, 0.32 * len(filas) + 1.2)))
    ys = np.arange(len(filas))
    for y, r in zip(ys, filas[::-1]):
        c = r["cox"]
        lo, hi = max(c["ic_inf"], 0.05), min(c["ic_sup"], 20)
        ax.plot([lo, hi], [y, y], color="C0", lw=1.2)
        ax.plot(c["punto"], y, "o", color="C0", ms=4)
    ax.axvline(1, color="0.5", lw=0.8)
    ax.set_xscale("log")
    ax.set_xlim(0.05, 20)
    ax.set_yticks(ys)
    ax.set_yticklabels([r["variable"] for r in filas[::-1]], fontsize=8)
    ax.set_xlabel("HR univariado (escala logarítmica)")
    ax.set_title("Cox univariado del compuesto a 90 días")
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def analizar(features, desenlaces):
    """Une los CSV, ajusta los modelos y devuelve el Markdown."""
    df = features.merge(desenlaces, on="person_id")
    df = preparar_tiempos_compuesto(df)
    predictores = lista_predictores(features.columns)
    resultados = ajustar_univariados(df, predictores)
    graficar_forest(resultados, "figuras/forest_univariado.png")
    return construir_informe(df, resultados)


if __name__ == "__main__":
    features = pd.read_csv("data/features_cohorte.csv")
    desenlaces = pd.read_csv("data/desenlaces_cohorte.csv")
    markdown = analizar(features, desenlaces)
    Path("docs").mkdir(exist_ok=True)
    Path("docs/univariado.md").write_text(markdown, encoding="utf-8")
    print(markdown)
