"""Calcula los desenlaces a 90 días de la cohorte 1701 y los guarda en un CSV."""
import sys
from pathlib import Path

import duckdb

from fragilidad.hfrs import leer_sql


def calcular_desenlaces(con):
    """Crea la tabla temporal 'cohorte' y devuelve los desenlaces por persona."""
    sql_cohorte = leer_sql("sql/02_cohorte.sql").strip().rstrip(";")
    con.execute(f"CREATE TEMP TABLE cohorte AS {sql_cohorte}")
    df = con.execute(leer_sql("sql/04_desenlaces.sql")).df()
    df["muerte"] = df["dias_muerte"].notna().astype(int)
    df["reingreso"] = df["dias_reingreso"].notna().astype(int)
    df["urgencias"] = df["dias_urgencias"].notna().astype(int)
    df["compuesto"] = (df[["muerte", "reingreso", "urgencias"]].sum(axis=1) > 0).astype(int)
    df["dias_compuesto"] = df[["dias_muerte", "dias_reingreso", "dias_urgencias"]].min(axis=1)
    df["seguimiento_completo"] = ((df["dias_seguimiento"] >= 90) | (df["muerte"] == 1)).astype(int)
    return df


if __name__ == "__main__":
    con = duckdb.connect(sys.argv[1], read_only=True)
    df = calcular_desenlaces(con)
    Path("data").mkdir(exist_ok=True)
    df.to_csv("data/desenlaces_cohorte.csv", index=False)
    print(len(df), "personas")
    print(df[["muerte", "reingreso", "urgencias", "compuesto"]].sum())
    print((df["seguimiento_completo"] == 0).sum(), "con seguimiento incompleto")
