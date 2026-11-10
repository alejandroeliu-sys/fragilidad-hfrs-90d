"""Calcula el HFRS de cada persona de la cohorte 1701 y lo guarda en un CSV."""
import sys
from pathlib import Path

import duckdb
import numpy as np


def leer_sql(ruta):
    """Lee un archivo .sql y devuelve su texto."""
    return Path(ruta).read_text(encoding="utf-8")


def categoria_hfrs(puntaje):
    """Categoría de Gilbert 2018: <5 bajo, 5-15 intermedio, >15 alto."""
    return np.select([puntaje < 5, puntaje <= 15], ["<5", "5-15"], default=">15")


def calcular_hfrs(con):
    """Crea la tabla temporal 'cohorte' y devuelve el HFRS por persona."""
    sql_cohorte = leer_sql("sql/02_cohorte.sql").strip().rstrip(";")
    con.execute(f"CREATE TEMP TABLE cohorte AS {sql_cohorte}")
    df = con.execute(leer_sql("sql/03_hfrs.sql")).df()
    columnas = ["hfrs", "hfrs_sin_f00", "hfrs_sin_social"]
    df[columnas] = df[columnas].round(1)
    df["categoria"] = categoria_hfrs(df["hfrs"])
    return df


if __name__ == "__main__":
    con = duckdb.connect(sys.argv[1], read_only=True)
    df = calcular_hfrs(con)
    Path("data").mkdir(exist_ok=True)
    df.to_csv("data/hfrs_cohorte.csv", index=False)
    print(len(df), "personas")
    print(df["hfrs"].describe())
    print(df["categoria"].value_counts())
