"""Pruebas de la validación MIMIC con datos de ejemplo"""
import numpy as np
import pandas as pd
import pytest

from fragilidad.validacion_mimic import (
    aplicar_m0,
    calcular_desenlaces,
    claves_icd9,
    codigos_hfrs_de_diagnostico,
    construir_cohorte,
    edad_en_fecha,
    hfrs_de_egreso,
    puntaje_desde_codigos,
)


def test_puntaje_hfrs_icd10_ajuste_f00_y_ventana():
    tabla = {"G30": 4.0, "F00": 7.1, "N39": 3.2, "Z73": 0.6}
    assert puntaje_desde_codigos({"G30"}, tabla) == pytest.approx(11.1)
    assert puntaje_desde_codigos({"G30", "G30"}, tabla) == pytest.approx(11.1)
    assert puntaje_desde_codigos({"Z73"}, tabla) == pytest.approx(0.6)
    assert puntaje_desde_codigos(set(), tabla) == pytest.approx(0.0)

    # Ventana de 730 días.
    admissions = pd.DataFrame(
        {
            "subject_id": [1, 1],
            "hadm_id": [10, 20],
            "dischtime": pd.to_datetime(["2020-06-01", "2018-06-01"]),
        }
    )
    diagnoses = pd.DataFrame(
        {
            "hadm_id": [10, 20],
            "icd_code": ["G30.9", "N39.0"],
            "icd_version": [10, 10],
        }
    )
    fila = {"subject_id": 1, "dischtime": pd.Timestamp("2020-06-01")}
    res = hfrs_de_egreso(fila, admissions, diagnoses, mapa_gem={}, tabla_puntos=tabla)
    assert res["hfrs"] == pytest.approx(11.1)
    assert res["n_dx_icd10"] == 1


def test_puntaje_hfrs_icd9_via_gem():
    tabla = {"G30": 4.0, "F00": 7.1}
    mapa = {"3310": {"G30"}}
    assert "3310" in claves_icd9("331.0")
    assert codigos_hfrs_de_diagnostico("3310", 9, mapa) == {"G30"}
    assert codigos_hfrs_de_diagnostico("331.0", 9, mapa) == {"G30"}
    assert codigos_hfrs_de_diagnostico("9999", 9, mapa) == set()
    admissions = pd.DataFrame(
        {
            "subject_id": [1],
            "hadm_id": [10],
            "dischtime": pd.to_datetime(["2020-06-01"]),
        }
    )
    diagnoses = pd.DataFrame(
        {"hadm_id": [10], "icd_code": ["3310"], "icd_version": [9]}
    )
    fila = {"subject_id": 1, "dischtime": pd.Timestamp("2020-06-01")}
    res = hfrs_de_egreso(fila, admissions, diagnoses, mapa_gem=mapa, tabla_puntos=tabla)
    assert res["hfrs"] == pytest.approx(11.1)
    assert res["n_dx_icd9"] == 1
    assert res["n_dx_icd9_mapeados"] == 1


def test_desenlaces_90d_y_m0_transportado():
    assert edad_en_fecha(70, 2100, "2102-03-01") == 72

    patients = pd.DataFrame(
        {
            "subject_id": [1, 2, 3, 4],
            "gender": ["M", "F", "M", "F"],
            "anchor_age": [80, 80, 80, 80],
            "anchor_year": [2100, 2100, 2100, 2100],
            "anchor_year_group": ["2011 - 2013"] * 4,
            "dod": pd.to_datetime(["2100-04-10", "NaT", "NaT", "NaT"]),
        }
    )
    # 1: egresa viva el 2100-02-01 y muere el día 68 (cuenta).
    # 2: reingreso el día 10; última evidencia el día 10 , seguimiento incompleto.
    # 3: urgencias el día 0  y otra el día 15; evidencia hasta el día 120.
    # 4: muerte el mismo día del egreso (intrahospitalaria; no entra a la cohorte).
    admissions = pd.DataFrame(
        {
            "subject_id": [1, 2, 2, 3, 4],
            "hadm_id": [11, 21, 22, 31, 41],
            "admittime": pd.to_datetime(
                ["2100-01-20", "2100-01-20", "2100-02-11", "2100-01-20", "2100-01-20"]
            ),
            "dischtime": pd.to_datetime(
                ["2100-02-01", "2100-02-01", "2100-02-15", "2100-02-01", "2100-02-01"]
            ),
            "deathtime": pd.to_datetime(["NaT", "NaT", "NaT", "NaT", "2100-02-01"]),
            "admission_type": ["EW EMER."] * 5,
            "discharge_location": ["HOME", "HOME", "HOME", "HOME", "DIED"],
            "hospital_expire_flag": [0, 0, 0, 0, 1],
        }
    )
    edstays = pd.DataFrame(
        {
            "subject_id": [3, 3],
            "hadm_id": [np.nan, np.nan],
            "intime": pd.to_datetime(["2100-02-01 18:00", "2100-02-16 00:00"]),
            "outtime": pd.to_datetime(["2100-02-01 20:00", "2100-06-01 00:00"]),
        }
    )
    indice = construir_cohorte(patients, admissions)
    assert set(indice["subject_id"]) == {1, 2, 3, 4}
    assert int(indice.loc[indice["subject_id"] == 4, "muerte_intrahospitalaria"].iloc[0]) == 1
    vivos = indice.loc[indice["muerte_intrahospitalaria"] == 0].copy()
    out = calcular_desenlaces(vivos, admissions, edstays, patients).set_index("subject_id")

    assert out.loc[1, "muerte"] == 1
    assert out.loc[1, "compuesto"] == 1
    assert out.loc[1, "seguimiento_completo"] == 1
    assert out.loc[1, "dias_muerte"] == 68

    assert out.loc[2, "reingreso"] == 1
    assert out.loc[2, "compuesto"] == 1
    assert out.loc[2, "seguimiento_completo"] == 0

    assert out.loc[3, "urgencias"] == 1
    assert out.loc[3, "dias_urgencias"] == 15
    assert out.loc[3, "seguimiento_completo"] == 1

    pred = aplicar_m0([10.0], 0.0, 0.1)
    assert pred[0] == pytest.approx(1.0 / (1.0 + np.exp(-1.0)))
