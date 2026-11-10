"""Pruebas de las funciones de la Tabla 1, los datos son solo de ejemplo."""
import numpy as np
import pandas as pd

from fragilidad.tabla1 import (
    construir_tabla1,
    elegir_prueba,
    formatear_p,
    resumir_categorica,
    resumir_continua,
    resumir_multinivel,
    texto_mediana_ric,
)


def test_resumir_continua_mediana_ric_y_faltantes_ejemplo():
    # Datos ejemplo
    x = pd.Series([1, 2, 3, 4, 5, np.nan])
    y = pd.Series([10, 11, 12, 13, 14])
    r = resumir_continua(x, y)

    assert texto_mediana_ric(pd.Series([1, 2, 3, 4, 5])) == "3.0 [2.0-4.0]"
    assert r["texto_x"] == "3.0 [2.0-4.0] (faltan 1)"
    assert r["texto_y"] == "12.0 [11.0-13.0]"
    assert r["faltan_x"] == 1
    assert r["faltan_y"] == 0
    assert r["prueba"] == "Mann-Whitney"
    assert r["p"] < 0.05


def test_elegir_prueba_fisher_y_chi_cuadrada_ejemplo():
    _, nombre = elegir_prueba([[50, 50], [50, 50]])
    assert nombre == "Chi-cuadrada"

    _, nombre = elegir_prueba([[8, 1], [2, 1]])
    assert nombre == "Fisher"

    _, nombre = elegir_prueba([[20, 1], [20, 1], [2, 1]])
    assert nombre == "Chi-cuadrada*"


def test_resumir_categorica_y_tabla_markdown_ejemplo():
    # Datos de ejemplo.
    x = pd.Series([0, 0, 0, 1, 1])
    y = pd.Series([1, 1, 1, 1, 0])
    r = resumir_categorica(x, y)
    assert r["texto_x"] == "2 (40.0 %)"
    assert r["texto_y"] == "4 (80.0 %)"
    assert r["p"] == r["p"]  
    assert r["prueba"] in {"Chi-cuadrada", "Fisher", "Chi-cuadrada*"}

    filas = resumir_multinivel(
        pd.Series(["<5", "<5", "5-15", "<5"]),
        pd.Series([">15", "5-15", "5-15", ">15"]),
        ["<5", "5-15", ">15"],
    )
    assert filas[0]["texto_x"] == "3 (75.0 %)"
    assert filas[0]["prueba"] in {"Chi-cuadrada", "Fisher", "Chi-cuadrada*", "—"}
    assert filas[1]["prueba"] == ""
    assert formatear_p(0.0004) == "<0.001"
    assert formatear_p(0.0312) == "0.031"

    # Tabla 1 de ejemplo.
    df = pd.DataFrame(
        {
            "muerte": [0, 0, 0, 1, 1],
            "edad": [70, 72, 68, 80, 85],
            "hombre": [1, 0, 1, 1, 0],
            "hfrs": [0.6, 1.2, 0.6, 8.0, 16.0],
            "categoria": ["<5", "<5", "<5", "5-15", ">15"],
            "dm2_prev": [0, 1, 0, 1, 1],
            "ic_prev": [0, 0, 0, 0, 1],
            "erc_prev": [0, 0, 0, 0, 0],
            "demencia_prev": [0, 0, 0, 1, 0],
            "creatinina": [0.9, 1.0, np.nan, 1.4, 1.6],
            "albumina": [4.0, 3.8, 4.1, 3.2, 3.0],
            "tfge": [np.nan, np.nan, np.nan, np.nan, np.nan],
            "hemoglobina": [13.0, 12.5, 14.0, 11.0, 10.5],
        }
    )
    texto = construir_tabla1(df)
    assert texto.startswith("# Tabla 1.")
    assert "| Variable | Sobrevive (n=3) | Muere (n=2) | p | Prueba |" in texto
    assert "Edad (años cumplidos)" in texto
    assert "Mann-Whitney" in texto
    assert "TFGe" in texto
    assert "(faltan 3)" in texto or "(faltan 2)" in texto
