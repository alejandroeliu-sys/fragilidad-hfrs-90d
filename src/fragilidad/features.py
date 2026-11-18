"""Constrir la matriz de features pre-índice de la cohorte y guardarla en un CSV."""
import sys
from pathlib import Path

import duckdb

from fragilidad.hfrs import leer_sql

# Valores que pueden faltar (no hubo medición en [-365, -1]). Representan (NULL) y se agregan "<nombre>_falta".
CON_FALTANTES = [
    "albumina_ultima", "creatinina_ultima", "urea_ultima", "hemoglobina_ultima",
    "tfge_ultima", "pas_ultima", "imc_ultimo",
]


def crear_cohorte(con):
    """Crea (o reemplaza) la tabla temporal 'cohorte' a partir de sql/02_cohorte.sql."""
    sql_cohorte = leer_sql("sql/02_cohorte.sql").strip().rstrip(";")
    con.execute(f"CREATE OR REPLACE TEMP TABLE cohorte AS {sql_cohorte}")


def agregar_indicadores_faltantes(df, columnas=CON_FALTANTES):
    """Agrega 'albumina_falta', 'pas_falta', etc.: 1 si el valor está vacío, 0 si no."""
    df = df.copy()
    for col in columnas:
        nombre = col.split("_")[0] + "_falta"
        df[nombre] = df[col].isna().astype(int)
    return df


def calcular_features(con):
    """Crea la cohorte, corre sql/03 (HFRS) y sql/06 (features) y los une por persona."""
    crear_cohorte(con)
    hfrs = con.execute(leer_sql("sql/03_hfrs.sql")).df()[["person_id", "hfrs"]]
    hfrs["hfrs"] = hfrs["hfrs"].round(1)

    df = con.execute(leer_sql("sql/06_features.sql")).df()
    df = df.merge(hfrs, on="person_id", how="left")
    df = agregar_indicadores_faltantes(df)

    # Una fila por persona: 
    if df["person_id"].duplicated().any():
        raise ValueError("Hay person_id repetidos en la matriz de features")
    return df


if __name__ == "__main__":
    con = duckdb.connect(sys.argv[1], read_only=True)
    df = calcular_features(con)
    Path("data").mkdir(exist_ok=True)
    df.to_csv("data/features_cohorte.csv", index=False)
    print("Dimensiones (filas, columnas):", df.shape)
    print("\n% faltante por columna (solo las que tienen faltantes):")
    faltante = (df.isna().mean() * 100).round(1)
    print(faltante[faltante > 0].to_string())
