"""Genera referencias/hfrs_icd9_gem.csv: pasar de codigo CIE-9 -> del código HFRS con al GEM CMS 2018."""
from pathlib import Path

import pandas as pd

RUTA_GEM = Path.home() / "datos" / "gem" / "2018_I9gem.txt"
RUTA_HFRS = Path("referencias/hfrs_codigos.csv")
RUTA_SALIDA = Path("referencias/hfrs_icd9_gem.csv")

codigos_hfrs = set(pd.read_csv(RUTA_HFRS)["codigo"].astype(str).str.upper())

filas = []
for linea in RUTA_GEM.read_text().splitlines():
    partes = linea.split()
    if len(partes) != 3 or partes[2][1] != "0":
        continue
    icd9, icd10 = partes[0], partes[1]
    tres = icd10[:3].upper()
    if tres in codigos_hfrs:
        filas.append((icd9, tres))

tabla = (
    pd.DataFrame(filas, columns=["icd9", "codigo"])
    .drop_duplicates()
    .sort_values(["icd9", "codigo"])
)
tabla.to_csv(RUTA_SALIDA, index=False)
print(f"{len(tabla):,} mapeos; {tabla['codigo'].nunique()} de {len(codigos_hfrs)} códigos HFRS cubiertos")
