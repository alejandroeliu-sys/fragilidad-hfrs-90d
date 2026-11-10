"""Pruebas del HFRS con datos de ejemplo"""
import pandas as pd
import pytest

from fragilidad.hfrs import categoria_hfrs, leer_sql


def test_categoria_hfrs_bordes():
    puntaje = pd.Series([4.9, 5, 15, 15.1], name="hfrs")
    categorias = list(categoria_hfrs(puntaje))
    assert categorias == ["<5", "5-15", "5-15", ">15"]


def _crear_mini_omop(con):
    """Base DuckDB de ejemplo, en memoria, con lo mínimo de OMOP."""
    con.execute(
        """
        CREATE TABLE person (
            person_id INTEGER,
            year_of_birth INTEGER
        );
        CREATE TABLE observation_period (
            person_id INTEGER,
            observation_period_start_date DATE,
            observation_period_end_date DATE
        );
        CREATE TABLE visit_occurrence (
            person_id INTEGER,
            visit_concept_id INTEGER,
            visit_start_date DATE,
            visit_end_date DATE
        );
        CREATE TABLE death (
            person_id INTEGER,
            death_date DATE
        );
        CREATE TABLE condition_occurrence (
            person_id INTEGER,
            condition_concept_id INTEGER,
            condition_start_date DATE
        );
        CREATE TABLE concept (
            concept_id INTEGER,
            concept_name VARCHAR,
            vocabulary_id VARCHAR,
            concept_code VARCHAR
        );
        CREATE TABLE concept_relationship (
            concept_id_1 INTEGER,
            concept_id_2 INTEGER,
            relationship_id VARCHAR,
            invalid_reason VARCHAR
        );
        """
    )

    # Fechas índice de ejemplo: 2020-06-01. La ventana HFRS es 730 días
    # hacia atrás
    con.execute(
        """
        CREATE TEMP TABLE cohorte AS
        SELECT * FROM (VALUES
            (1, DATE '2020-06-01', DATE '2020-08-30'),
            (2, DATE '2020-06-01', DATE '2020-08-30'),
            (3, DATE '2020-06-01', DATE '2020-08-30'),
            (4, DATE '2020-06-01', DATE '2020-08-30'),
            (5, DATE '2020-06-01', DATE '2020-08-30')
        ) t(subject_id, cohort_start_date, cohort_end_date);
        """
    )

    # Conceptos de ejemplo:
    # 1001 SNOMED "Alzheimer's disease"  -> ICD10CM G30.9 
    # 1002 SNOMED "Stress"               -> ICD10CM Z73.3
    # 1003 SNOMED "Familial Alzheimer's disease of early onset" 
    con.execute(
        """
        INSERT INTO concept VALUES
            (1001, 'Alzheimer''s disease', 'SNOMED', '26929004'),
            (2001, 'Alzheimer''s disease', 'ICD10CM', 'G30.9'),
            (1002, 'Stress', 'SNOMED', '73595000'),
            (2002, 'Stress', 'ICD10CM', 'Z73.3'),
            (1003, 'Familial Alzheimer''s disease of early onset', 'SNOMED', '1237069005'),
            (1004, 'Alzheimer''s disease', 'SNOMED', '26929004');
        INSERT INTO concept_relationship VALUES
            (1001, 2001, 'Mapped from', NULL),
            (1002, 2002, 'Mapped from', NULL);
        INSERT INTO condition_occurrence VALUES
            -- Persona 1: G30 dentro de la ventana -> 4.0 + 7.1 de F00
            (1, 1001, DATE '2020-01-15'),
            -- Persona 2: Z73 el día índice -> 0.6, y 0 en hfrs_sin_social
            (2, 1002, DATE '2020-06-01'),
            -- Persona 3: Alzheimer familiar sin traducción, entra por el puente
            (3, 1003, DATE '2019-06-01'),
            -- Persona 4: sin diagnósticos
            -- Persona 5: G30 un día antes de la ventana (731 días) -> no cuenta
            (5, 1001, DATE '2018-06-01');
        """
    )


def test_sql_hfrs_ajuste_f00_y_sensibilidad():
    """Integración de sql/03_hfrs.sql sobre una mini base de ejemplo."""
    import duckdb

    con = duckdb.connect(":memory:")
    _crear_mini_omop(con)
    resultado = con.execute(leer_sql("sql/03_hfrs.sql")).df()
    resultado = resultado.sort_values("person_id").reset_index(drop=True)
    por_persona = resultado.set_index("person_id")

    assert list(resultado["person_id"]) == [1, 2, 3, 4, 5]

    # Persona 1 : G30 4.0 + ajuste F00 7.1 = 11.1
    assert por_persona.loc[1, "hfrs"] == pytest.approx(11.1)
    assert por_persona.loc[1, "hfrs_sin_f00"] == pytest.approx(4.0)
    assert por_persona.loc[1, "hfrs_sin_social"] == pytest.approx(11.1)

    # Persona 2 : solo Z73 = 0.6; sin códigos sociales 0
    assert por_persona.loc[2, "hfrs"] == pytest.approx(0.6)
    assert por_persona.loc[2, "hfrs_sin_f00"] == pytest.approx(0.6)
    assert por_persona.loc[2, "hfrs_sin_social"] == pytest.approx(0.0)

    # Persona 3 : puente manual a G30, mismo ajuste F00
    assert por_persona.loc[3, "hfrs"] == pytest.approx(11.1)
    assert por_persona.loc[3, "hfrs_sin_f00"] == pytest.approx(4.0)

    # Persona 4 : sin diagnósticos, puntaje 0
    assert por_persona.loc[4, "hfrs"] == pytest.approx(0.0)
    assert por_persona.loc[4, "hfrs_sin_f00"] == pytest.approx(0.0)
    assert por_persona.loc[4, "hfrs_sin_social"] == pytest.approx(0.0)

    # Persona 5 : diagnóstico un día fuera de la ventana
    assert por_persona.loc[5, "hfrs"] == pytest.approx(0.0)
