"""Pruebas de la matriz de features con datos de ejemplo (no son la cohorte real)."""
from pathlib import Path

import duckdb
import pandas as pd

from fragilidad.features import agregar_indicadores_faltantes, calcular_features

# Dos personas de ejemplo con egreso (día 0) el 2020-06-01
SQL_COHORTE_EJEMPLO = """
SELECT * FROM (VALUES
    (1, DATE '2020-06-01', DATE '2020-08-30'),
    (2, DATE '2020-06-01', DATE '2020-08-30')
) t(subject_id, cohort_start_date, cohort_end_date)
"""
# HFRS de ejemplo.
SQL_HFRS_EJEMPLO = "SELECT subject_id AS person_id, 6.24 AS hfrs FROM cohorte"


def test_indicadores_faltantes():
    df = pd.DataFrame({"albumina_ultima": [3.5, None], "pas_ultima": [None, 120.0]})
    df = agregar_indicadores_faltantes(df, ["albumina_ultima", "pas_ultima"])
    assert list(df["albumina_falta"]) == [0, 1]
    assert list(df["pas_falta"]) == [1, 0]
    assert df["albumina_ultima"].isna().sum() == 1 


def test_calcular_features_ventanas_sin_fuga(monkeypatch):
    def leer_sql_ejemplo(ruta):
        nombre = Path(ruta).name
        if nombre == "02_cohorte.sql":
            return SQL_COHORTE_EJEMPLO
        if nombre == "03_hfrs.sql":
            return SQL_HFRS_EJEMPLO
        return Path(ruta).read_text(encoding="utf-8")

    monkeypatch.setattr("fragilidad.features.leer_sql", leer_sql_ejemplo)

    con = duckdb.connect(":memory:")
    con.execute(
        """
        CREATE TABLE person (person_id INTEGER, gender_concept_id INTEGER,
            year_of_birth INTEGER, month_of_birth INTEGER, day_of_birth INTEGER);
        CREATE TABLE observation_period (person_id INTEGER,
            observation_period_start_date DATE, observation_period_end_date DATE);
        CREATE TABLE condition_occurrence (person_id INTEGER,
            condition_concept_id INTEGER, condition_start_date DATE);
        CREATE TABLE concept_ancestor (ancestor_concept_id INTEGER,
            descendant_concept_id INTEGER);
        CREATE TABLE concept (concept_id INTEGER, concept_class_id VARCHAR);
        CREATE TABLE drug_exposure (person_id INTEGER, drug_concept_id INTEGER,
            drug_exposure_start_date DATE);
        CREATE TABLE measurement (measurement_id INTEGER, person_id INTEGER,
            measurement_concept_id INTEGER, measurement_date DATE, value_as_number DOUBLE);
        CREATE TABLE visit_occurrence (person_id INTEGER, visit_concept_id INTEGER,
            visit_start_date DATE, visit_end_date DATE);

        INSERT INTO person VALUES
            -- Persona 1: hombre; cumple 80 el 2 de junio, un día después del egreso
            (1, 8507, 1940, 6, 2),
            (2, 8532, 1950, 1, 1);
        INSERT INTO observation_period VALUES
            (1, DATE '2019-06-01', DATE '2021-01-01'),
            (2, DATE '2018-01-01', DATE '2021-01-01');
        INSERT INTO condition_occurrence VALUES
            (1, 201826, DATE '2020-05-31'),  -- DM2 el día -1: cuenta
            (2, 316139, DATE '2020-06-01');  -- IC el día 0: no cuenta
        INSERT INTO concept VALUES (1503297, 'Ingredient');
        INSERT INTO concept_ancestor VALUES (1503297, 1503297);
        INSERT INTO drug_exposure VALUES
            -- Metformina en dos fechas distintas dentro de [-365, -1]
            (1, 1503297, DATE '2020-03-01'),
            (1, 1503297, DATE '2020-05-20');
        INSERT INTO measurement VALUES
            (10, 1, 3024561, DATE '2020-05-22', 3.1),   -- albúmina día -10: es la última válida
            (11, 1, 3024561, DATE '2020-06-01', 2.0),   -- albúmina día 0: se excluye (fuga)
            (12, 2, 3051825, DATE '2020-06-01', 1.5);   -- creatinina solo el día 0: queda vacía
        INSERT INTO visit_occurrence VALUES
            (1, 9201, DATE '2020-05-27', DATE '2020-06-01'),  -- estancia índice de 5 días
            (1, 9201, DATE '2020-02-01', DATE '2020-02-04'),  -- hospitalización previa
            (1, 9203, DATE '2020-06-15', DATE '2020-06-15'),  -- urgencias posterior: no cuenta
            (2, 9202, DATE '2020-04-01', DATE '2020-04-01');  -- consulta ambulatoria
        """
    )

    df = calcular_features(con).set_index("person_id")

    assert df.index.is_unique
    assert not {"muerte_90d", "muerte", "compuesto", "dias_muerte"} & set(df.columns)
    assert df.loc[1, "edad"] == 79  
    assert df.loc[1, "sexo_masc"] == 1
    assert df.loc[1, "obs_previa_dias"] == 366
    assert df.loc[1, "dm2_dx"] == 1
    assert df.loc[2, "ic_dx"] == 0
    assert df.loc[1, "dm_inferida"] == 1
    assert df.loc[1, "albumina_ultima"] == 3.1
    assert df.loc[1, "albumina_n"] == 1
    assert pd.isna(df.loc[2, "creatinina_ultima"])
    assert df.loc[2, "creatinina_falta"] == 1
    assert df.loc[1, "n_hosp_365"] == 1
    assert df.loc[1, "n_urgencias_365"] == 0
    assert df.loc[2, "n_ambulatorias_365"] == 1
    assert df.loc[1, "estancia_indice_dias"] == 5
    assert pd.isna(df.loc[2, "estancia_indice_dias"])
    assert df.loc[1, "hfrs"] == 6.2 
