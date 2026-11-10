"""Arma la Tabla 1 del avance: características según muerte a 90 días."""
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, fisher_exact, mannwhitneyu

from fragilidad.hfrs import categoria_hfrs, leer_sql

# No se llaman calcular_hfrs ni calcular_desenlaces: cada uno hace
# CREATE TEMP TABLE cohorte y chocaría con la otra consulta.
# Aquí se crea la cohorte una sola vez y se corren sql/03, sql/04 y sql/05.


def crear_cohorte(con):
    """Crea (o reemplaza) la tabla temporal 'cohorte' a partir de sql/02_cohorte.sql."""
    sql_cohorte = leer_sql("sql/02_cohorte.sql").strip().rstrip(";")
    con.execute(f"CREATE OR REPLACE TEMP TABLE cohorte AS {sql_cohorte}")


def agregar_eventos(df):
    """Agrega las columnas 0/1 de evento a la salida de sql/04_desenlaces.sql."""
    df = df.copy()
    df["muerte"] = df["dias_muerte"].notna().astype(int)
    df["reingreso"] = df["dias_reingreso"].notna().astype(int)
    df["urgencias"] = df["dias_urgencias"].notna().astype(int)
    df["compuesto"] = (df[["muerte", "reingreso", "urgencias"]].sum(axis=1) > 0).astype(int)
    df["dias_compuesto"] = df[["dias_muerte", "dias_reingreso", "dias_urgencias"]].min(axis=1)
    df["seguimiento_completo"] = ((df["dias_seguimiento"] >= 90) | (df["muerte"] == 1)).astype(int)
    return df


def armar_analitico(con):
    """Une características, HFRS y desenlaces. Devuelve solo seguimiento completo."""
    crear_cohorte(con)

    hfrs = con.execute(leer_sql("sql/03_hfrs.sql")).df()
    hfrs[["hfrs", "hfrs_sin_f00", "hfrs_sin_social"]] = hfrs[
        ["hfrs", "hfrs_sin_f00", "hfrs_sin_social"]
    ].round(1)
    hfrs["categoria"] = categoria_hfrs(hfrs["hfrs"])

    desenlaces = agregar_eventos(con.execute(leer_sql("sql/04_desenlaces.sql")).df())
    caracteristicas = con.execute(leer_sql("sql/05_caracteristicas.sql")).df()

    df = caracteristicas.merge(hfrs, on="person_id", how="inner")
    df = df.merge(desenlaces, on="person_id", how="inner")
    return df.loc[df["seguimiento_completo"] == 1].copy()


def texto_mediana_ric(valores):
    """Devuelve 'mediana [q25-q75]' con un decimal, o un guion si no hay datos."""
    if len(valores) == 0:
        return "—"
    mediana = valores.median()
    q25 = valores.quantile(0.25)
    q75 = valores.quantile(0.75)
    return f"{mediana:.1f} [{q25:.1f}-{q75:.1f}]"


def resumir_continua(x, y):
    """Compara dos grupos numéricos: mediana [RIC], faltantes y Mann-Whitney a dos colas.

    x es el grupo que sobrevive (muerte = 0) y y el que muere (muerte = 1).
    Los valores vacíos se excluyen del test y se cuentan como faltantes.
    """
    x_ok = pd.to_numeric(x, errors="coerce").dropna()
    y_ok = pd.to_numeric(y, errors="coerce").dropna()
    faltan_x = int(pd.to_numeric(x, errors="coerce").isna().sum())
    faltan_y = int(pd.to_numeric(y, errors="coerce").isna().sum())

    texto_x = texto_mediana_ric(x_ok)
    texto_y = texto_mediana_ric(y_ok)
    if faltan_x > 0:
        texto_x = f"{texto_x} (faltan {faltan_x})"
    if faltan_y > 0:
        texto_y = f"{texto_y} (faltan {faltan_y})"

    if len(x_ok) > 0 and len(y_ok) > 0:
        _, p = mannwhitneyu(x_ok, y_ok, alternative="two-sided")
        prueba = "Mann-Whitney"
    else:
        p = np.nan
        prueba = "—"
    return {
        "texto_x": texto_x,
        "texto_y": texto_y,
        "p": p,
        "prueba": prueba,
        "faltan_x": faltan_x,
        "faltan_y": faltan_y,
    }


def elegir_prueba(observados):
    """Elige Chi-cuadrada o Fisher a partir de una tabla de frecuencias observadas.

    Fisher se usa solo en tablas 2x2 con alguna frecuencia esperada menor a 5.
    En tablas más grandes con esperadas menores a 5 se devuelve Chi-cuadrada
    y un asterisco, para advertirlo en la nota al pie.
    """
    tabla = np.asarray(observados, dtype=float)
    if tabla.size == 0 or tabla.min() < 0 or tabla.sum() == 0:
        return np.nan, "—"
    # Una fila o columna nula no deja calcular la prueba.
    if (tabla.sum(axis=0) == 0).any() or (tabla.sum(axis=1) == 0).any():
        return np.nan, "—"

    _, p_chi, _, esperadas = chi2_contingency(tabla)
    hay_esperada_chica = (esperadas < 5).any()

    if tabla.shape == (2, 2) and hay_esperada_chica:
        _, p_fisher = fisher_exact(tabla)
        return p_fisher, "Fisher"
    if hay_esperada_chica:
        return p_chi, "Chi-cuadrada*"
    return p_chi, "Chi-cuadrada"


def texto_n_porcentaje(conteo, total):
    """Devuelve 'n (xx.x %)' respecto del total del grupo."""
    if total == 0:
        return "—"
    porcentaje = 100 * conteo / total
    return f"{int(conteo)} ({porcentaje:.1f} %)"


def resumir_categorica(x, y, positivo=1):
    """Compara una variable 0/1: n (%) del valor positivo y prueba de independencia."""
    x = pd.Series(x)
    y = pd.Series(y)
    n_x = int((x == positivo).sum())
    n_y = int((y == positivo).sum())
    texto_x = texto_n_porcentaje(n_x, len(x))
    texto_y = texto_n_porcentaje(n_y, len(y))
    observados = [
        [int((x != positivo).sum()), int((y != positivo).sum())],
        [n_x, n_y],
    ]
    p, prueba = elegir_prueba(observados)
    return {"texto_x": texto_x, "texto_y": texto_y, "p": p, "prueba": prueba}


def resumir_multinivel(x, y, niveles):
    """Compara una categórica con varios niveles. Devuelve una fila por nivel.

    El valor p y el nombre de la prueba van solo en la primera fila.
    """
    x = pd.Series(x)
    y = pd.Series(y)
    observados = []
    filas = []
    for nivel in niveles:
        n_x = int((x == nivel).sum())
        n_y = int((y == nivel).sum())
        observados.append([n_x, n_y])
        filas.append(
            {
                "nivel": nivel,
                "texto_x": texto_n_porcentaje(n_x, len(x)),
                "texto_y": texto_n_porcentaje(n_y, len(y)),
            }
        )
    # Se quitan los niveles con cero personas en ambos grupos para no anular la prueba.
    observados_test = [fila for fila in observados if fila[0] + fila[1] > 0]
    p, prueba = elegir_prueba(observados_test)
    filas[0]["p"] = p
    filas[0]["prueba"] = prueba
    for fila in filas[1:]:
        fila["p"] = None
        fila["prueba"] = ""
    return filas


def formatear_p(p):
    """Formatea el valor p con tres decimales, o '<0.001' si es más chico."""
    if p is None:
        return ""
    if pd.isna(p):
        return "—"
    if p < 0.001:
        return "<0.001"
    return f"{p:.3f}"


def _fila_markdown(variable, texto_x, texto_y, p, prueba):
    return f"| {variable} | {texto_x} | {texto_y} | {formatear_p(p)} | {prueba} |"


def _agregar_continua(lineas, etiqueta, x, y):
    r = resumir_continua(x, y)
    lineas.append(_fila_markdown(etiqueta, r["texto_x"], r["texto_y"], r["p"], r["prueba"]))
    return r


def _agregar_categorica(lineas, etiqueta, x, y):
    r = resumir_categorica(x, y)
    lineas.append(_fila_markdown(etiqueta, r["texto_x"], r["texto_y"], r["p"], r["prueba"]))
    return r


def construir_tabla1(df):
    """Arma el Markdown de la Tabla 1 comparando sobrevivientes y fallecidos."""
    vive = df[df["muerte"] == 0]
    muere = df[df["muerte"] == 1]
    n_vive = len(vive)
    n_muere = len(muere)

    lineas = [
        "# Tabla 1. Características basales según muerte a 90 días",
        "",
        f"| Variable | Sobrevive (n={n_vive:,}) | Muere (n={n_muere:,}) | p | Prueba |",
        "|---|---:|---:|---:|---|",
    ]
    uso_asterisco = False

    _agregar_continua(lineas, "Edad (años cumplidos)", vive["edad"], muere["edad"])
    r = _agregar_categorica(lineas, "Hombre", vive["hombre"], muere["hombre"])
    uso_asterisco = uso_asterisco or r["prueba"] == "Chi-cuadrada*"
    _agregar_continua(lineas, "HFRS", vive["hfrs"], muere["hfrs"])

    filas_cat = resumir_multinivel(
        vive["categoria"], muere["categoria"], ["<5", "5-15", ">15"]
    )
    uso_asterisco = uso_asterisco or filas_cat[0]["prueba"] == "Chi-cuadrada*"
    etiquetas_hfrs = [
        "Categoría HFRS: <5",
        "Categoría HFRS: 5-15",
        "Categoría HFRS: >15",
    ]
    for etiqueta, fila in zip(etiquetas_hfrs, filas_cat):
        lineas.append(
            _fila_markdown(
                etiqueta, fila["texto_x"], fila["texto_y"], fila["p"], fila["prueba"]
            )
        )

    for etiqueta, columna in [
        ("Diabetes mellitus tipo 2 previa", "dm2_prev"),
        ("Insuficiencia cardiaca previa", "ic_prev"),
        ("Enfermedad renal crónica previa", "erc_prev"),
        ("Demencia previa", "demencia_prev"),
    ]:
        r = _agregar_categorica(lineas, etiqueta, vive[columna], muere[columna])
        uso_asterisco = uso_asterisco or r["prueba"] == "Chi-cuadrada*"

    for etiqueta, columna in [
        ("Creatinina", "creatinina"),
        ("Albúmina", "albumina"),
        ("TFGe", "tfge"),
        ("Hemoglobina", "hemoglobina"),
    ]:
        _agregar_continua(lineas, etiqueta, vive[columna], muere[columna])

    for etiqueta, columna in [
        ("Con creatinina", "creatinina"),
        ("Con albúmina", "albumina"),
        ("Con TFGe", "tfge"),
        ("Con hemoglobina", "hemoglobina"),
    ]:
        r = _agregar_categorica(
            lineas,
            etiqueta,
            vive[columna].notna().astype(int),
            muere[columna].notna().astype(int),
        )
        uso_asterisco = uso_asterisco or r["prueba"] == "Chi-cuadrada*"

    lineas.append("")
    lineas.append(
        "Las variables continuas se resumen como mediana [rango intercuartílico] "
        "y se comparan con la prueba de Mann-Whitney a dos colas. Las categóricas "
        "se presentan como n (%) y se comparan con chi cuadrada, o con Fisher si la "
        "tabla es 2×2 y alguna frecuencia esperada es menor a 5."
    )
    if uso_asterisco:
        lineas.append("")
        lineas.append("Nota: el asterisco indica chi cuadrada con alguna frecuencia esperada menor a 5.")
    lineas.append("")
    return "\n".join(lineas)


if __name__ == "__main__":
    con = duckdb.connect(sys.argv[1], read_only=True)
    df = armar_analitico(con)
    markdown = construir_tabla1(df)
    Path("docs").mkdir(exist_ok=True)
    Path("docs/tabla1.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    print(len(df), "personas con seguimiento completo")
    print(int(df["muerte"].sum()), "muertes a 90 días")
