"""Tabla de atrición a partir de sql/02_cohorte.sql."""
import sys
import duckdb
import pandas as pd

PASOS = [
    ("evento_inicial", "Primer egreso hospitalario a los 65 años o más"),
    ("observacion_previa", "+ 730 días de observación previa"),
    ("lavado", "+ sin hospitalización en los 30 días previos"),
    ("inc1", "+ 2 visitas ambulatorias o más en 365 días"),
    ("inc2", "+ creatinina en 365 días"),
    ("inc3", "+ albúmina sérica en 365 días"),
    ("inc4", "+ tasa de filtración glomerular en 365 días"),
    ("inc5", "+ multimorbilidad (2 dx o más en 730 días)"),
    ("exc2", "− cáncer maligno en 365 días"),
    ("exc1", "− muerte el día del egreso o antes"),
]

def armar_tabla(conteos):
    """Convierte la lista de conteos en una tabla con % y pérdidas."""
    tabla = pd.DataFrame({"paso": [d for _, d in PASOS], "n": conteos})
    tabla["pct_inicial"] = (100 * tabla["n"] / tabla["n"].iloc[0]).round(1)
    tabla["perdidos"] = (-tabla["n"].diff()).fillna(0).astype(int)
    return tabla


def contar_atricion(con, sql_cohorte):
    """Cuenta cuántas personas quedan después de cada CTE de la cohorte."""
    ctes = sql_cohorte[: sql_cohorte.index("-- PASO 6")].rstrip().rstrip(",")
    conteos = ", ".join(f"(SELECT COUNT(*) FROM {cte}) AS {cte}" for cte, _ in PASOS)
    fila = con.sql(f"{ctes}\nSELECT {conteos}").fetchall()[0]
    return armar_tabla(list(fila))


def a_markdown(tabla):
    """Escribe la tabla en formato Markdown, sin librerías extra."""
    lineas = ["| paso | n | % del inicial | perdidos |", "|---|---:|---:|---:|"]
    for _, f in tabla.iterrows():
        lineas.append(f"| {f['paso']} | {f['n']:,} | {f['pct_inicial']} % | {f['perdidos']:,} |")
    return "\n".join(lineas)


if __name__ == "__main__":
    con = duckdb.connect(sys.argv[1], read_only=True)
    tabla = contar_atricion(con, open("sql/02_cohorte.sql").read())
    print(tabla.to_string(index=False))
    with open("docs/atricion.md", "w") as f:
        f.write("# Tabla de atrición — cohorte 1701\n\n" + a_markdown(tabla) + "\n")
