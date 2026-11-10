"""Análisis preliminar de supervivencia: muerte a 90 días según el HFRS."""
import sys
from pathlib import Path

import duckdb

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from lifelines import CoxPHFitter, KaplanMeierFitter
from lifelines.plotting import add_at_risk_counts
from lifelines.statistics import (
    multivariate_logrank_test,
    pairwise_logrank_test,
    proportional_hazard_test,
)

from fragilidad.hfrs import categoria_hfrs, leer_sql
from fragilidad.tabla1 import agregar_eventos, crear_cohorte, formatear_p

ORDEN_CATEGORIA = ["<5", "5-15", ">15"]


def preparar_tiempos(df):
    """Define el tiempo y el evento para la supervivencia a 90 días.

    Si la persona murió, el tiempo es dias_muerte y el evento vale 1.
    Si no murió, el tiempo es el mínimo entre dias_seguimiento y 90,
    y el evento vale 0 (censura). Se usa toda la cohorte, también
    quien se pierde de vista antes de los 90 días.
    """
    df = df.copy()
    murio = df["muerte"] == 1
    df["evento"] = murio.astype(int)
    tiempo_censura = np.minimum(df["dias_seguimiento"], 90)
    df["tiempo"] = np.where(murio, df["dias_muerte"], tiempo_censura)
    return df


def asignar_terciles(hfrs):
    """Corta el HFRS en hasta tres grupos con los terciles de la muestra.

    pd.qcut con duplicates='drop' no inventa cortes cuando hay empates:
    si muchos puntajes valen lo mismo, pueden salir menos de tres grupos.
    Si todos los valores son iguales, queda un solo grupo T1.
    Devuelve las etiquetas (T1, T2, ...), los cortes y el número de grupos.
    """
    hfrs = pd.Series(hfrs)
    categorias, cortes = pd.qcut(hfrs, 3, duplicates="drop", retbins=True)
    n_grupos = len(categorias.cat.categories)
    if n_grupos == 0:
        etiquetas = pd.Series(["T1"] * len(hfrs), index=hfrs.index)
        return etiquetas, cortes, 1
    nombres = [f"T{i}" for i in range(1, n_grupos + 1)]
    etiquetas = categorias.cat.rename_categories(nombres)
    return etiquetas, cortes, n_grupos


def armar_datos_supervivencia(con):
    """Une HFRS, desenlaces, edad y sexo, y prepara tiempos. Usa toda la cohorte."""
    crear_cohorte(con)

    hfrs = con.execute(leer_sql("sql/03_hfrs.sql")).df()
    hfrs["hfrs"] = hfrs["hfrs"].round(1)
    hfrs["categoria"] = categoria_hfrs(hfrs["hfrs"])

    desenlaces = agregar_eventos(con.execute(leer_sql("sql/04_desenlaces.sql")).df())
    basales = con.execute(leer_sql("sql/05_caracteristicas.sql")).df()
    basales = basales[["person_id", "edad", "hombre"]]

    df = basales.merge(hfrs[["person_id", "hfrs", "categoria"]], on="person_id")
    df = df.merge(desenlaces, on="person_id")
    df = preparar_tiempos(df)
    terciles, cortes, n_terciles = asignar_terciles(df["hfrs"])
    df["tercil"] = terciles
    return df, cortes, n_terciles


def resumir_seguimiento(df):
    """Cuenta personas, muertes y la mediana del tiempo observado."""
    return {
        "n": int(len(df)),
        "eventos": int(df["evento"].sum()),
        "mediana_tiempo": float(df["tiempo"].median()),
        "q25_tiempo": float(df["tiempo"].quantile(0.25)),
        "q75_tiempo": float(df["tiempo"].quantile(0.75)),
    }


def prueba_logrank(df, columna_grupo):
    """Log-rank de varios grupos (multivariate_logrank_test)."""
    resultado = multivariate_logrank_test(
        df["tiempo"], df[columna_grupo], df["evento"]
    )
    return {
        "estadistico": float(resultado.test_statistic),
        "gl": int(resultado.degrees_of_freedom),
        "p": float(resultado.p_value),
    }


def prueba_logrank_pares(df, columna_grupo):
    """Log-rank por pares. Devuelve una lista de dicts, uno por comparación."""
    resultado = pairwise_logrank_test(df["tiempo"], df[columna_grupo], df["evento"])
    filas = []
    for indice, fila in resultado.summary.iterrows():
        filas.append(
            {
                "grupo_a": str(indice[0]),
                "grupo_b": str(indice[1]),
                "estadistico": float(fila["test_statistic"]),
                "p": float(fila["p"]),
            }
        )
    return filas


def graficar_km(df, columna_grupo, orden, ruta, titulo):
    """Dibuja Kaplan-Meier con IC 95 % y, si se puede, la tabla de en riesgo."""
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 7))
    ajustados = []
    for grupo in orden:
        sub = df[df[columna_grupo] == grupo]
        if sub.empty:
            continue
        kmf = KaplanMeierFitter()
        kmf.fit(sub["tiempo"], sub["evento"], label=f"{grupo} (n={len(sub)})")
        kmf.plot_survival_function(ax=ax, ci_show=True)
        ajustados.append(kmf)

    ax.set_xlim(0, 90)
    ax.set_xticks([0, 30, 60, 90])
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("Días desde el egreso")
    ax.set_ylabel("Probabilidad de supervivencia")
    ax.set_title(titulo)
    ax.grid(True, alpha=0.3)

    con_tabla_riesgo = False
    if ajustados:
        try:
            # Se cuenta a quienes están en riesgo al inicio de cada marca
            # (si se cuenta al final, el día 90 queda en 0 por la censura).
            add_at_risk_counts(
                *ajustados,
                ax=ax,
                xticks=[0, 30, 60, 90],
                rows_to_show=["At risk"],
                at_risk_count_from_start_of_period=True,
            )
            con_tabla_riesgo = True
        except Exception:
            con_tabla_riesgo = False
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)
    return con_tabla_riesgo


def extraer_hr(modelo):
    """Saca HR, IC 95 % y p de un Cox ya ajustado."""
    filas = []
    for variable, fila in modelo.summary.iterrows():
        filas.append(
            {
                "variable": str(variable),
                "hr": float(fila["exp(coef)"]),
                "ic_inf": float(fila["exp(coef) lower 95%"]),
                "ic_sup": float(fila["exp(coef) upper 95%"]),
                "p": float(fila["p"]),
            }
        )
    return filas


def prueba_riesgos_proporcionales(modelo, datos):
    """Prueba de riesgos proporcionales (transformación rank) por covariable."""
    resultado = proportional_hazard_test(modelo, datos, time_transform="rank")
    filas = []
    for variable, fila in resultado.summary.iterrows():
        filas.append(
            {
                "variable": str(variable),
                "estadistico": float(fila["test_statistic"]),
                "p": float(fila["p"]),
            }
        )
    return filas


def ajustar_cox(df, formula):
    """Ajusta un Cox y devuelve el modelo, las HR, el C-index y la prueba PH.

    Si el modelo no puede estimarse (por ejemplo, un covariable sin variación),
    devuelve None y un mensaje con la causa.
    """
    columnas = ["tiempo", "evento", "hfrs", "edad", "hombre", "tercil"]
    datos = df[columnas].dropna().copy()
    try:
        modelo = CoxPHFitter()
        modelo.fit(datos, duration_col="tiempo", event_col="evento", formula=formula)
    except Exception as error:
        return None, str(error)
    return {
        "modelo": modelo,
        "hr": extraer_hr(modelo),
        "c_index": float(modelo.concordance_index_),
        "ph": prueba_riesgos_proporcionales(modelo, datos),
    }, None


def _linea_logrank(nombre, res):
    return (
        f"| {nombre} | {res['estadistico']:.2f} | {res['gl']} | "
        f"{formatear_p(res['p'])} |"
    )


def construir_informe(df, cortes, n_terciles, resultados):
    """Arma el Markdown con n, log-rank, HR, C-index, PH y limitaciones."""
    s = resultados["seguimiento"]
    n_alto = int((df["categoria"] == ">15").sum())
    eventos_alto = int(((df["categoria"] == ">15") & (df["evento"] == 1)).sum())
    recuento_terciles = df["tercil"].value_counts().sort_index()
    cortes_texto = ", ".join(f"{c:.1f}" for c in cortes)

    lineas = [
        "# Supervivencia a 90 días según el HFRS",
        "",
        "## Seguimiento",
        "",
        f"- Personas: {s['n']:,}",
        f"- Muertes a 90 días: {s['eventos']:,} "
        f"({100 * s['eventos'] / s['n']:.1f} %)",
        f"- Mediana del tiempo observado: {s['mediana_tiempo']:.1f} días "
        f"[{s['q25_tiempo']:.1f}-{s['q75_tiempo']:.1f}]",
        "",
        "El tiempo de las personas que murieron es el día de la muerte. "
        "El de las demás es el mínimo entre el seguimiento y 90 días "
        "(censura, incluida quien se pierde de vista antes de los 90 días).",
        "",
        "## Terciles de la muestra",
        "",
        f"Se pidieron 3 terciles con `pd.qcut(..., duplicates='drop')`. "
        f"Resultado: **{n_terciles}** grupo(s). Cortes: {cortes_texto}.",
        "",
    ]
    for nombre, n in recuento_terciles.items():
        lineas.append(f"- {nombre}: {int(n):,} personas")
    if n_terciles < 3:
        lineas.extend(
            [
                "",
                "Hay muchos empates en el HFRS, así que los terciles no se "
                "pudieron cortar en tres grupos. No se inventaron cortes: "
                "se usan los grupos que realmente salieron.",
            ]
        )

    lineas.extend(
        [
            "",
            "## Log-rank",
            "",
            "| Comparación | Estadístico | gl | p |",
            "|---|---:|---:|---:|",
        ]
    )
    if resultados["logrank_categoria"] is not None:
        lineas.append(
            _linea_logrank("Categorías HFRS (global)", resultados["logrank_categoria"])
        )
    else:
        lineas.append("| Categorías HFRS (global) | — | — | — |")
    for par in resultados["logrank_pares"]:
        lineas.append(
            f"| {par['grupo_a']} vs {par['grupo_b']} | "
            f"{par['estadistico']:.2f} | 1 | {formatear_p(par['p'])} |"
        )
    if resultados["logrank_terciles"] is not None:
        lineas.append(
            _linea_logrank("Terciles (global)", resultados["logrank_terciles"])
        )
    elif n_terciles < 2:
        lineas.append(
            "| Terciles (global) | — | — | — |"
        )

    lineas.extend(
        [
            "",
            "## Modelos de Cox",
            "",
            "| Modelo | Variable | HR | IC 95 % | p | C-index |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for modelo in resultados["cox"]:
        if modelo["error"]:
            lineas.append(
                f"| {modelo['nombre']} | — | — | — | — | — |"
            )
            continue
        first = True
        for fila in modelo["ajuste"]["hr"]:
            c_index = f"{modelo['ajuste']['c_index']:.3f}" if first else ""
            first = False
            lineas.append(
                f"| {modelo['nombre']} | {fila['variable']} | "
                f"{fila['hr']:.2f} | {fila['ic_inf']:.2f}-{fila['ic_sup']:.2f} | "
                f"{formatear_p(fila['p'])} | {c_index} |"
            )

    for modelo in resultados["cox"]:
        if modelo["error"]:
            lineas.extend(
                [
                    "",
                    f"El modelo «{modelo['nombre']}» no se pudo estimar: "
                    f"{modelo['error']}",
                ]
            )

    lineas.extend(
        [
            "",
            "## Prueba de riesgos proporcionales (transformación rank)",
            "",
            "| Modelo | Variable | Estadístico | p |",
            "|---|---|---:|---:|",
        ]
    )
    hay_ph = False
    for modelo in resultados["cox"]:
        if modelo["error"] or modelo["ajuste"] is None or modelo["ph"] is None:
            continue
        hay_ph = True
        for fila in modelo["ajuste"]["ph"]:
            lineas.append(
                f"| {modelo['nombre']} | {fila['variable']} | "
                f"{fila['estadistico']:.2f} | {formatear_p(fila['p'])} |"
            )
    if not hay_ph:
        lineas.append("| — | — | — | — |")

    lineas.extend(
        [
            "",
            "## Limitaciones",
            "",
            f"El grupo de HFRS alto (>15) tiene {n_alto} personas "
            f"({eventos_alto} muertes). La curva de Kaplan-Meier y el "
            "log-rank de ese grupo son inestables; por eso se informan "
            "también el HFRS continuo (HR por cada punto) y los terciles "
            "de la muestra. La mediana de supervivencia no se alcanza a "
            "los 90 días si la curva se queda por encima de 0.5.",
            "",
        ]
    )
    if resultados.get("nota_riesgo") is False:
        lineas.extend(
            [
                "No se pudo dibujar la tabla de personas en riesgo en las figuras.",
                "",
            ]
        )
    return "\n".join(lineas)


def analizar(con):
    """Corre todo el análisis y devuelve el Markdown y los datos."""
    df, cortes, n_terciles = armar_datos_supervivencia(con)
    seguimiento = resumir_seguimiento(df)

    orden_terciles = [f"T{i}" for i in range(1, n_terciles + 1)]
    tabla_cat = graficar_km(
        df,
        "categoria",
        ORDEN_CATEGORIA,
        "figuras/km_muerte_hfrs.png",
        "Kaplan-Meier de muerte a 90 días según la categoría de HFRS",
    )
    tabla_ter = graficar_km(
        df,
        "tercil",
        orden_terciles,
        "figuras/km_muerte_terciles.png",
        "Kaplan-Meier de muerte a 90 días según terciles de HFRS",
    )

    categorias_presentes = df["categoria"].nunique()
    logrank_categoria = None
    logrank_pares = []
    if categorias_presentes >= 2:
        logrank_categoria = prueba_logrank(df, "categoria")
        logrank_pares = prueba_logrank_pares(df, "categoria")

    logrank_terciles = None
    if n_terciles >= 2:
        logrank_terciles = prueba_logrank(df, "tercil")

    cox = []
    ajuste, error = ajustar_cox(df, "hfrs")
    cox.append({"nombre": "HFRS continuo, univariable", "ajuste": ajuste, "error": error, "ph": True})
    ajuste, error = ajustar_cox(df, "hfrs + edad + hombre")
    cox.append({"nombre": "HFRS continuo, ajustado por edad y sexo", "ajuste": ajuste, "error": error, "ph": True})
    if n_terciles >= 2:
        ajuste, error = ajustar_cox(df, "C(tercil, Treatment('T1'))")
        cox.append({"nombre": "Terciles (referencia T1)", "ajuste": ajuste, "error": error, "ph": False})

    resultados = {
        "seguimiento": seguimiento,
        "logrank_categoria": logrank_categoria,
        "logrank_pares": logrank_pares,
        "logrank_terciles": logrank_terciles,
        "cox": cox,
        "nota_riesgo": tabla_cat and tabla_ter,
    }
    markdown = construir_informe(df, cortes, n_terciles, resultados)
    return markdown, df, resultados


if __name__ == "__main__":
    con = duckdb.connect(sys.argv[1], read_only=True)
    markdown, _, _ = analizar(con)
    Path("docs").mkdir(exist_ok=True)
    Path("docs/supervivencia.md").write_text(markdown, encoding="utf-8")
    print(markdown)
