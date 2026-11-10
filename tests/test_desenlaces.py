"""Pruebas de desenlaces a 90 días con datos de ejemplo."""
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from fragilidad.desenlaces import calcular_desenlaces


SQL_COHORTE_EJEMPLO = """
SELECT * FROM (VALUES
    (1, DATE '2020-06-01', DATE '2020-08-30'),
    (2, DATE '2020-06-01', DATE '2020-08-30'),
    (3, DATE '2020-06-01', DATE '2020-07-15'),
    (4, DATE '2020-06-01', DATE '2020-08-30')
) t(subject_id, cohort_start_date, cohort_end_date)
"""


def test_calcular_desenlaces_columnas_de_evento(monkeypatch):
    """Mini base de ejemplo: muerte, reingreso, urgencias y seguimiento."""

    def leer_sql_ejemplo(ruta):
        if Path(ruta).name == "02_cohorte.sql":
            return SQL_COHORTE_EJEMPLO
        return Path(ruta).read_text(encoding="utf-8")

    monkeypatch.setattr("fragilidad.desenlaces.leer_sql", leer_sql_ejemplo)

    con = duckdb.connect(":memory:")
    con.execute(
        """
        CREATE TABLE death (person_id INTEGER, death_date DATE);
        CREATE TABLE visit_occurrence (
            person_id INTEGER,
            visit_concept_id INTEGER,
            visit_start_date DATE,
            visit_end_date DATE
        );
        INSERT INTO death VALUES
            -- Persona 1 (ejemplo): muere a los 10 días (dentro de 90)
            (1, DATE '2020-06-11'),
            -- Fuera de ventana: el día del egreso no cuenta, ni después del día 90
            (2, DATE '2020-06-01'),
            (4, DATE '2020-08-31');
        INSERT INTO visit_occurrence VALUES
            -- Persona 2 (ejemplo): reingreso (9201) a los 5 días
            (2, 9201, DATE '2020-06-06', DATE '2020-06-10'),
            -- Persona 2 también va a urgencias (9203) a los 20 días; el compuesto toma el 5
            (2, 9203, DATE '2020-06-21', DATE '2020-06-21'),
            -- Persona 3 (ejemplo): solo urgencias a los 7 días; seguimiento de 44 días, vivo
            (3, 9203, DATE '2020-06-08', DATE '2020-06-08'),
            -- Visita ambulatoria 9202: no es reingreso ni urgencias
            (4, 9202, DATE '2020-06-10', DATE '2020-06-10');
        """
    )

    df = calcular_desenlaces(con).sort_values("person_id").set_index("person_id")

    assert list(df["muerte"]) == [1, 0, 0, 0]
    assert list(df["reingreso"]) == [0, 1, 0, 0]
    assert list(df["urgencias"]) == [0, 1, 1, 0]
    assert list(df["compuesto"]) == [1, 1, 1, 0]
    assert df.loc[1, "dias_muerte"] == 10
    assert df.loc[2, "dias_reingreso"] == 5
    assert df.loc[2, "dias_urgencias"] == 20
    assert df.loc[2, "dias_compuesto"] == 5
    assert df.loc[3, "dias_urgencias"] == 7
    assert df.loc[1, "dias_seguimiento"] == 90
    assert df.loc[3, "dias_seguimiento"] == 44
    # Completo si hay 90 días de observación o si murió en ese periodo.
    assert list(df["seguimiento_completo"]) == [1, 1, 0, 1]
    assert pd.isna(df.loc[4, "dias_compuesto"])
    assert pytest.approx(df["compuesto"].sum()) == 3
