"""Validación externa de M0 (HFRS solo) en la demo pública de MIMIC-IV."""
import argparse
import sys
from datetime import timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from fragilidad.hfrs import categoria_hfrs
from fragilidad.modelos import (
    LOGISTICA,
    auroc,
    calibracion,
    ic_bootstrap,
    texto_ic,
)

SEMILLA = 42
N_BOOT = 1000
VENTANA_HFRS_DIAS = 730
N_MIN_EVENTOS = 10
N_DESARROLLO_TESIS = 5372

RUTA_MIMIC_DEFECTO = Path.home() / "datos" / "mimic-iv-demo"
RUTA_ED_DEFECTO = Path.home() / "datos" / "mimic-iv-ed-demo"
RUTA_HFRS = Path("referencias/hfrs_codigos.csv")
RUTA_GEM = Path("referencias/hfrs_icd9_gem.csv")

TIPOS_INDICE = (
    "EW EMER.",
    "URGENT",
    "ELECTIVE",
    "DIRECT EMER.",
    "SURGICAL SAME DAY ADMISSION",
    "OBSERVATION ADMIT",
)

# Variables de M3 y por qué sí o no se transportan a la demo.
DISPONIBILIDAD = (
    ("hfrs", "M0", "Sí", "ICD-10 nativo (3 caracteres) más GEM CMS 2018 para ICD-9."),
    ("edad", "M1", "Sí", "anchor_age + (año del egreso − anchor_year). Los 89+ suelen aparecer como 91."),
    ("sexo_masc", "M1", "Sí", "Columna gender de patients."),
    ("dm2_dx, ic_dx, erc_dx, demencia_dx, cardiop_isq_dx, hta_dx, anemia_dx", "M2", "Parcial", "Habría que redefinir los mapas en ICD-9/ICD-10; el SQL del proyecto usa SNOMED/OMOP de Synthea."),
    ("n_ingredientes_365, n_ingredientes_30", "M2", "No", "Son recuentos de ingredientes OMOP de Synthea. En MIMIC hay prescriptions, pero no es el mismo concepto."),
    ("dm_inferida, hta_inferida, ic_inferida", "M2", "No", "Reglas de fármacos construidas sobre el formulario de Synthea."),
    ("albumina_ultima, creatinina_ultima, urea_ultima, hemoglobina_ultima, tfge_ultima, pendientes, n, de", "M3", "Parcial", "labevents existe y se podría mapear por itemid; no se implementó para no fingir un transporte."),
    ("pas_ultima, imc_ultimo", "M3", "Parcial", "Aparecen en omr y en registros de urgencias; hace falta un mapeo que aquí no se hace."),
    ("n_ambulatorias_365", "M3", "No", "MIMIC-IV es un recorte hospitalario; no hay consultas ambulatorias comparables a Synthea."),
    ("n_hosp_365, n_urgencias_365", "M3", "Parcial", "Se pueden contar admissions y edstays previas; no se transporta M3."),
    ("estancia_indice_dias", "M3", "Sí", "dischtime − admittime del ingreso índice."),
    ("urea_falta, hemoglobina_falta, pas_falta, imc_falta", "M3", "Parcial", "Dependen de que los laboratorios o signos se hayan mapeado."),
)


def buscar_archivo(raiz, nombre):
    """Encuentra un archivo por nombre bajo la carpeta descargada (da igual el anidamiento)."""
    raiz = Path(raiz).expanduser()
    if not raiz.exists():
        return None
    if raiz.is_file() and raiz.name == nombre:
        return raiz
    directo = raiz / nombre
    if directo.is_file():
        return directo
    hallados = sorted(raiz.rglob(nombre))
    return hallados[0] if hallados else None


def leer_tabla_hfrs(ruta=RUTA_HFRS):
    df = pd.read_csv(ruta)
    return {str(c).strip().upper(): float(p) for c, p in zip(df["codigo"], df["puntos"])}


def leer_mapa_gem(ruta=RUTA_GEM):
    """icd9 (sin punto, como en el GEM) → conjunto de códigos HFRS de 3 caracteres."""
    df = pd.read_csv(ruta, dtype=str)
    mapa = {}
    for icd9, codigo in zip(df["icd9"], df["codigo"]):
        mapa.setdefault(str(icd9).strip().upper(), set()).add(str(codigo).strip().upper())
    return mapa


def prefijo_icd10(codigo):
    return str(codigo).replace(".", "").upper()[:3]


def claves_icd9(codigo):
    """Variantes sin punto y con ceros a la izquierda (MIMIC vs GEM)."""
    crudo = str(codigo).replace(".", "").upper().strip()
    claves = {crudo}
    if not crudo:
        return claves
    if crudo[0].isalpha():
        cuerpo = crudo[1:]
        for ancho in (3, 4, 5):
            claves.add(crudo[0] + cuerpo.zfill(max(0, ancho - 1)))
        claves.add(crudo[0] + cuerpo.lstrip("0"))
    else:
        for ancho in (3, 4, 5):
            claves.add(crudo.zfill(ancho))
        claves.add(crudo.lstrip("0") or "0")
    return claves


def codigos_hfrs_de_diagnostico(icd_code, icd_version, mapa_gem):
    """Conjunto de códigos HFRS (3 caracteres) que aporta un diagnóstico."""
    version = int(icd_version)
    if version == 10:
        return {prefijo_icd10(icd_code)}
    if version == 9:
        for clave in claves_icd9(icd_code):
            if clave in mapa_gem:
                return set(mapa_gem[clave])
        return set()
    return set()


def puntaje_desde_codigos(codigos, tabla_puntos, ajustar_f00=True):
    """Suma puntos únicos; si hay G30 se agrega F00 (convenio OMS, igual que en el proyecto)."""
    presente = {str(c).upper() for c in codigos}
    if ajustar_f00 and "G30" in presente:
        presente.add("F00")
    puntos = sum(tabla_puntos[c] for c in presente if c in tabla_puntos)
    return float(np.round(puntos, 1))


def cargar_tablas(ruta_mimic, ruta_ed):
    """Lee patients, admissions, diagnoses_icd y edstays desde la demo descomprimida."""
    patients_p = buscar_archivo(ruta_mimic, "patients.csv.gz")
    admissions_p = buscar_archivo(ruta_mimic, "admissions.csv.gz")
    diagnoses_p = buscar_archivo(ruta_mimic, "diagnoses_icd.csv.gz")
    edstays_p = buscar_archivo(ruta_ed, "edstays.csv.gz")
    faltan = [
        nombre
        for nombre, ruta in (
            ("hosp/patients.csv.gz", patients_p),
            ("hosp/admissions.csv.gz", admissions_p),
            ("hosp/diagnoses_icd.csv.gz", diagnoses_p),
            ("ed/edstays.csv.gz", edstays_p),
        )
        if ruta is None
    ]
    if faltan:
        raise FileNotFoundError(
            "No se encontraron: "
            + ", ".join(faltan)
            + f". ¿Están descomprimidas las demos en {ruta_mimic} y {ruta_ed}?"
        )
    patients = pd.read_csv(patients_p, parse_dates=["dod"])
    admissions = pd.read_csv(
        admissions_p, parse_dates=["admittime", "dischtime", "deathtime"]
    )
    diagnoses = pd.read_csv(diagnoses_p)
    edstays = pd.read_csv(edstays_p, parse_dates=["intime", "outtime"])
    return patients, admissions, diagnoses, edstays


def edad_en_fecha(anchor_age, anchor_year, fecha):
    """Edad aproximada en MIMIC: el año ancla está desplazado, el intervalo se conserva."""
    return anchor_age + (pd.Timestamp(fecha).year - int(anchor_year))


def construir_cohorte(patients, admissions, tipos=TIPOS_INDICE):
    """Primer egreso con edad ≥ 65 en un ingreso de tipo hospitalario."""
    df = admissions.merge(
        patients[["subject_id", "gender", "anchor_age", "anchor_year", "anchor_year_group", "dod"]],
        on="subject_id",
        how="left",
    )
    df["edad_egreso"] = [
        edad_en_fecha(a, y, t) for a, y, t in zip(df["anchor_age"], df["anchor_year"], df["dischtime"])
    ]
    candidatos = df.loc[df["admission_type"].isin(tipos) & (df["edad_egreso"] >= 65)].copy()
    candidatos = candidatos.sort_values(["subject_id", "dischtime"])
    indice = candidatos.drop_duplicates("subject_id", keep="first").reset_index(drop=True)
    indice["muerte_intrahospitalaria"] = (
        (indice["hospital_expire_flag"] == 1)
        | indice["deathtime"].notna()
        | (indice["discharge_location"] == "DIED")
    ).astype(int)
    indice["sexo_masc"] = (indice["gender"] == "M").astype(int)
    indice["edad"] = indice["edad_egreso"]
    return indice


def _dias_entero(fin, inicio):
    """Diferencia en días de calendario (como DATE_DIFF)."""
    return int((pd.Timestamp(fin).normalize() - pd.Timestamp(inicio).normalize()).days)


def desenlaces_de_un_egreso(fila, admissions, edstays, patients):
    """Muerte, reingreso o urgencias en días 1-90 después del egreso (estricto, como en el SQL)."""
    t0 = pd.Timestamp(fila["dischtime"])
    sid = fila["subject_id"]
    hadm = fila["hadm_id"]
    t90 = t0 + timedelta(days=90)

    dias_muerte = np.nan
    dod = patients.loc[patients["subject_id"] == sid, "dod"]
    dod = dod.iloc[0] if len(dod) else pd.NaT
    if pd.notna(dod):
        d = _dias_entero(dod, t0)
        if 1 <= d <= 90:
            dias_muerte = d
    posteriores_muerte = admissions[
        (admissions["subject_id"] == sid)
        & (admissions["hadm_id"] != hadm)
        & admissions["deathtime"].notna()
    ]
    for deathtime in posteriores_muerte["deathtime"]:
        d = _dias_entero(deathtime, t0)
        if 1 <= d <= 90:
            dias_muerte = d if pd.isna(dias_muerte) else min(int(dias_muerte), d)

    reingresos = admissions[
        (admissions["subject_id"] == sid)
        & (admissions["hadm_id"] != hadm)
        & (admissions["admittime"] > t0)
        & (admissions["admittime"] <= t90)
    ]
    dias_reingreso = np.nan
    if len(reingresos):
        dias = reingresos["admittime"].map(lambda t: _dias_entero(t, t0))
        validos = dias[(dias >= 1) & (dias <= 90)]
        if len(validos):
            dias_reingreso = int(validos.min())

    urgencias = edstays[
        (edstays["subject_id"] == sid)
        & (edstays["intime"] > t0)
        & (edstays["intime"] <= t90)
    ]
    if "hadm_id" in urgencias.columns:
        urgencias = urgencias[urgencias["hadm_id"].fillna(-1) != hadm]
    dias_urgencias = np.nan
    if len(urgencias):
        dias = urgencias["intime"].map(lambda t: _dias_entero(t, t0))
        validos = dias[(dias >= 1) & (dias <= 90)]
        if len(validos):
            dias_urgencias = int(validos.min())

    evidencias = [t0]
    ultimo_egreso = admissions.loc[admissions["subject_id"] == sid, "dischtime"].max()
    if pd.notna(ultimo_egreso):
        evidencias.append(pd.Timestamp(ultimo_egreso))
    if len(edstays):
        ultimo_ed = edstays.loc[edstays["subject_id"] == sid, "outtime"].max()
        if pd.notna(ultimo_ed):
            evidencias.append(pd.Timestamp(ultimo_ed))
    if pd.notna(dod):
        evidencias.append(pd.Timestamp(dod))
    dias_seguimiento = _dias_entero(max(evidencias), t0)

    muerte = int(pd.notna(dias_muerte))
    reingreso = int(pd.notna(dias_reingreso))
    urgencia = int(pd.notna(dias_urgencias))
    compuesto = int(muerte or reingreso or urgencia)
    seguimiento_completo = int((dias_seguimiento >= 90) or muerte)
    return {
        "dias_muerte": dias_muerte,
        "dias_reingreso": dias_reingreso,
        "dias_urgencias": dias_urgencias,
        "dias_seguimiento": dias_seguimiento,
        "muerte": muerte,
        "reingreso": reingreso,
        "urgencias": urgencia,
        "compuesto": compuesto,
        "seguimiento_completo": seguimiento_completo,
    }


def calcular_desenlaces(cohorte, admissions, edstays, patients):
    filas = [desenlaces_de_un_egreso(r, admissions, edstays, patients) for _, r in cohorte.iterrows()]
    return pd.concat([cohorte.reset_index(drop=True), pd.DataFrame(filas)], axis=1)


def hfrs_de_egreso(fila, admissions, diagnoses, mapa_gem, tabla_puntos, ventana=VENTANA_HFRS_DIAS):
    """HFRS con diagnósticos de ingresos cuyo egreso cae en [índice − 730, índice]."""
    t0 = pd.Timestamp(fila["dischtime"])
    inicio = t0 - timedelta(days=int(ventana))
    ventana_adm = admissions[
        (admissions["subject_id"] == fila["subject_id"])
        & (admissions["dischtime"] >= inicio)
        & (admissions["dischtime"] <= t0)
    ]
    dx = diagnoses[diagnoses["hadm_id"].isin(ventana_adm["hadm_id"])]
    codigos = set()
    n_icd9 = n_icd10 = n_icd9_mapeados = 0
    for rec in dx.itertuples(index=False):
        version = int(rec.icd_version)
        hallados = codigos_hfrs_de_diagnostico(rec.icd_code, version, mapa_gem)
        if version == 9:
            n_icd9 += 1
            if hallados:
                n_icd9_mapeados += 1
        elif version == 10:
            n_icd10 += 1
        codigos |= hallados
    return {
        "hfrs": puntaje_desde_codigos(codigos, tabla_puntos),
        "n_dx_icd9": n_icd9,
        "n_dx_icd10": n_icd10,
        "n_dx_icd9_mapeados": n_icd9_mapeados,
        "n_codigos_hfrs": int(sum(c in tabla_puntos for c in (codigos | ({"F00"} if "G30" in codigos else set())))),
    }


def calcular_hfrs_cohorte(cohorte, admissions, diagnoses, mapa_gem, tabla_puntos):
    filas = [
        hfrs_de_egreso(r, admissions, diagnoses, mapa_gem, tabla_puntos)
        for _, r in cohorte.iterrows()
    ]
    out = pd.concat([cohorte.reset_index(drop=True), pd.DataFrame(filas)], axis=1)
    out["categoria"] = categoria_hfrs(out["hfrs"])
    return out

def ajustar_m0(features, desenlaces):
    """Logística M0 en unidades naturales (sin estandarizar) sobre el desarrollo local."""
    df = features.merge(desenlaces, on="person_id")
    if "seguimiento_completo" not in df.columns or "compuesto" not in df.columns:
        raise ValueError("Los CSV de desarrollo deben traer compuesto y seguimiento_completo.")
    logist = df.loc[df["seguimiento_completo"] == 1, ["hfrs", "compuesto"]].dropna()
    y = logist["compuesto"].to_numpy(dtype=int)
    x = logist[["hfrs"]].to_numpy(dtype=float)
    n = len(logist)
    eventos = int(y.sum())
    if n < 2 or np.unique(y).size < 2 or np.unique(x).size < 2:
        return {
            "intercepto": np.nan,
            "coef_hfrs": np.nan,
            "n": n,
            "eventos": eventos,
            "prevalencia": float(y.mean()) if n else np.nan,
            "ajustable": False,
        }
    modelo = LogisticRegression(**LOGISTICA)
    modelo.fit(x, y)
    return {
        "intercepto": float(modelo.intercept_[0]),
        "coef_hfrs": float(modelo.coef_[0, 0]),
        "n": n,
        "eventos": eventos,
        "prevalencia": float(y.mean()),
        "ajustable": True,
    }


def aplicar_m0(hfrs, intercepto, coef_hfrs):
    """Probabilidad predicha por el M0 de Synthea: sigmoid(intercepto + coef * HFRS)."""
    hfrs = np.asarray(hfrs, dtype=float)
    logit = intercepto + coef_hfrs * hfrs
    return 1.0 / (1.0 + np.exp(-logit))


def metricas_externas(y, predichos, n_grupos=5):
    """AUROC con IC bootstrap, pendiente, calibración-en-lo-grande y razón O/E."""
    y = np.asarray(y, dtype=int)
    p = np.asarray(predichos["M0"], dtype=float)
    metricas = ic_bootstrap(y, predichos, n_boot=N_BOOT, semilla=SEMILLA, referencia="M0")
    n_grupos = max(2, min(n_grupos, int(max(2, len(y) // 5))))
    cal = calibracion(y, p, n_grupos=n_grupos)
    esperado = float(p.sum())
    observado = float(y.sum())
    return {
        "metricas": metricas,
        "pendiente": cal["pendiente"],
        "citl": cal["citl"],
        "oe": observado / esperado if esperado > 0 else np.nan,
        "observado": observado,
        "esperado": esperado,
        "cal": cal,
    }


def graficar_hfrs_vs_synthea(hfrs_mimic, hfrs_synthea, ruta):
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    bins = np.arange(0, max(15, float(np.nanmax(hfrs_mimic)) + 2, float(np.nanmax(hfrs_synthea)) + 2), 2)
    ax.hist(hfrs_synthea, bins=bins, alpha=0.55, color="#4C72B0", label="Synthea (desarrollo)", density=True)
    ax.hist(hfrs_mimic, bins=bins, alpha=0.55, color="#C44E52", label="MIMIC-IV Demo", density=True)
    ax.set(xlabel="HFRS", ylabel="Densidad", title="Distribución del HFRS: desarrollo vs MIMIC-IV Demo")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def graficar_roc(y, predichos, ruta):
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 7))
    for nombre, p in predichos.items():
        from sklearn.metrics import roc_curve

        fpr, tpr, _ = roc_curve(y, p)
        ax.plot(fpr, tpr, label=f"{nombre} (AUROC {auroc(y, p):.3f})")
    ax.plot([0, 1], [0, 1], ls="--", color="0.5", lw=0.8)
    ax.set(
        xlabel="1 − especificidad",
        ylabel="Sensibilidad",
        title="ROC de M0 transportado (MIMIC-IV Demo)",
        xlim=(0, 1),
        ylim=(0, 1),
    )
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def graficar_calibracion(y, predichos, ruta, n_grupos=5):
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 7))
    for nombre, p in predichos.items():
        cal = calibracion(y, p, n_grupos=n_grupos)
        ax.plot(cal["predicho"], cal["observado"], "o-", label=nombre)
    ax.plot([0, 1], [0, 1], ls="--", color="0.5", lw=0.8)
    ax.set(
        xlabel="Probabilidad predicha (media del grupo)",
        ylabel="Fracción observada",
        title="Calibración de M0 transportado (MIMIC-IV Demo)",
        xlim=(0, 1),
        ylim=(0, 1),
    )
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def _fmt(x, dec=1):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:.{dec}f}"


def _resumen_num(serie):
    s = pd.Series(serie, dtype=float)
    return {
        "n": int(s.notna().sum()),
        "media": float(s.mean()),
        "de": float(s.std(ddof=1)) if s.notna().sum() > 1 else np.nan,
        "mediana": float(s.median()),
        "p25": float(s.quantile(0.25)),
        "p75": float(s.quantile(0.75)),
        "min": float(s.min()),
        "max": float(s.max()),
    }

def construir_informe(conteos, hfrs_mimic, hfrs_synthea, m0, ext, aviso_desarrollo):
    """Markdown con agregados (nunca identificadores de persona)."""
    cats = pd.Series(categoria_hfrs(pd.Series(hfrs_mimic))).value_counts()
    r_m = _resumen_num(hfrs_mimic)
    r_s = _resumen_num(hfrs_synthea)
    lineas = [
        "# Validación externa en MIMIC-IV Demo",
        "",
        "Se transporta solo M0 (HFRS) ajustado en Synthea hacia la *MIMIC-IV Clinical Database Demo* v2.2, "
        "complementada con la *MIMIC-IV-ED Demo* v2.2 para las visitas a urgencias que no se convierten en ingreso. "
        "Ambas son de acceso abierto en PhysioNet, licencia ODbL v1.0, y se leen desde una ruta **fuera del repositorio** "
        "(por defecto `~/datos/mimic-iv-demo` y `~/datos/mimic-iv-ed-demo`). En este documento no hay identificadores de persona.",
        "",
        "En el conjunto de desarrollo de la tesis (Synthea, n = 5,372 con seguimiento completo, prevalencia 37.4 %) "
        "el AUROC fuera de pliegue fue 0.600 (M0), 0.734 (M3) y 0.810 (XGBoost).;",
    ]
    if aviso_desarrollo:
        lineas += [aviso_desarrollo, ""]

    lineas += [
        "## Cómo se construyó la cohorte en la demo",
        "",
        "- Edad al egreso: `anchor_age + (año del dischtime − anchor_year)`. El año ancla está desplazado por paciente; "
        "los intervalos relativos se conservan. Las edades de 89 años o más suelen aparecer como 91",
        "- Índice: primer egreso con edad ≥ 65 en un ingreso de tipo hospitalario "
        f"({', '.join(TIPOS_INDICE)}). Se excluyen `EU OBSERVATION`, `DIRECT OBSERVATION` y `AMBULATORY OBSERVATION`.",
        "- Se excluyen las muertes intrahospitalarias del índice (`hospital_expire_flag`, `deathtime` o `discharge_location = DIED`), "
        "porque el proyecto define la muerte postegreso con `death_date > cohort_start_date`.",
        "- Desenlaces a 90 días, días 1-90 de calendario (no se cuenta el día 0): muerte (`dod` o un `deathtime` posterior), "
        "reingreso (otro `admittime`) o urgencias (`edstays.intime` de la demo de ED).",
        "- El `dod` de MIMIC no es un seguimiento vital completo. El seguimiento se considera completo si hay "
        "un encuentro o un `dod` en o después del día 90, o si se observó la muerte (igual que en el proyecto: "
        "un reingreso o una urgencia por sí solos no cierran el seguimiento).",
        "- Ventana del HFRS: diagnósticos de todos los ingresos cuyo `dischtime` cae en los 730 días hasta el egreso índice, inclusive. "
        "En MIMIC el diagnóstico no tiene fecha propia, solo `hadm_id`.",
        "- El HFRS de Gilbert 2018 es de ICD-10 (109 códigos de 3 caracteres, más el ajuste G30 → F00). "
        "En la demo, la mayoría de los ingresos índice de 65+ están codificados en ICD-9 (era 2011-2013 / 2014-2016, "
        "Ocho códigos HFRS no tienen origen ICD-9 en el GEM "
        "(F00, J22, R02, R54, U80, X59, Y95, Z50); F00 se sigue asignando cuando aparece G30.",
        "",
        "## Conteo (agregados de la demo)",
        "",
        f"- Pacientes en la demo clínica: {conteos['n_pacientes_demo']}.",
        f"- Ingresos de cualquier tipo con edad ≥ 65 al egreso: {conteos['n_ingresos_65']} "
        f"({conteos['n_personas_65']} personas).",
        f"- Personas con al menos un egreso índice hospitalario ≥ 65: {conteos['n_indice']}.",
        f"- Muertes en el ingreso índice (excluidas del análisis postegreso): {conteos['n_muerte_indice']}.",
        f"- Cohorte postegreso (egresadas vivas): {conteos['n_cohorte']}.",
        f"- De ellas, el ingreso índice era solo ICD-9: {conteos['n_indice_solo_icd9']}; "
        f"solo ICD-10: {conteos['n_indice_solo_icd10']}.",
        f"- Diagnósticos en la ventana HFRS: {conteos['n_dx_icd9']} ICD-9 "
        f"({conteos['n_dx_icd9_mapeados']} mapearon a algún código HFRS) y {conteos['n_dx_icd10']} ICD-10.",
        f"- Eventos a 90 días en la cohorte postegreso (n = {conteos['n_cohorte']}): "
        f"muerte {conteos['n_muerte']}, reingreso {conteos['n_reingreso']}, urgencias {conteos['n_urgencias']}, "
        f"compuesto {conteos['n_compuesto']}.",
        f"- Seguimiento completo (regla del proyecto): {conteos['n_completo']} personas, "
        f"con {conteos['n_compuesto_completo']} eventos (prevalencia {conteos['prev_completo']:.1%}).",
        f"- Personas con evento compuesto pero seguimiento incompleto (no entran al AUROC): {conteos['n_evento_incompleto']}.",
        "",
        "Son pocos eventos. Los intervalos de confianza serán anchos; esta validación es exploratoria, no confirmatoria.",
        "",
        "## Distribución del HFRS frente a Synthea",
        "",
        "![HFRS en Synthea y en MIMIC-IV Demo](../figuras/hfrs_mimic_vs_synthea.png)",
        "",
        "| Conjunto | n | Media | DE | Mediana | P25 | P75 | Mín | Máx |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| Synthea (desarrollo, seguimiento completo) | {r_s['n']} | {_fmt(r_s['media'], 2)} | {_fmt(r_s['de'], 2)} | {_fmt(r_s['mediana'], 2)} | {_fmt(r_s['p25'], 2)} | {_fmt(r_s['p75'], 2)} | {_fmt(r_s['min'], 2)} | {_fmt(r_s['max'], 2)} |",
        f"| MIMIC-IV Demo (cohorte postegreso) | {r_m['n']} | {_fmt(r_m['media'], 2)} | {_fmt(r_m['de'], 2)} | {_fmt(r_m['mediana'], 2)} | {_fmt(r_m['p25'], 2)} | {_fmt(r_m['p75'], 2)} | {_fmt(r_m['min'], 2)} | {_fmt(r_m['max'], 2)} |",
        "",
        "Categorías de Gilbert 2018 en la cohorte MIMIC postegreso: "
        f"<5 = {int(cats.get('<5', 0))}, 5-15 = {int(cats.get('5-15', 0))}, >15 = {int(cats.get('>15', 0))}.",
        "",
        "La demo es un hospital terciario real; Synthea es sintético y en esta corrida el HFRS de desarrollo puede "
        "estar mucho más concentrado en valores bajos. Esa diferencia de distribución, por sí sola, ya avisa que "
        "la calibración del M0 puede fallar aunque la discriminación se conserve.",
        "",
    ]

    lineas += [
        "## ¿Se puede validar M0?",
        "",
    ]
    if ext is None:
        lineas += [
            f"No se reporta AUROC de transporte: {conteos['motivo_no_validar']}",
            "",
        ]
    else:
        auc = texto_ic(ext["metricas"]["M0"]["auroc"])
        lineas += [
            f"Sí, con precaución: hay {conteos['n_compuesto_completo']} eventos en "
            f"{conteos['n_completo']} personas con seguimiento completo (umbral preespecificado: ≥ {N_MIN_EVENTOS} eventos). "
            "Se aplican los coeficientes de Synthea, sin reajustar en MIMIC.",
            "",
            f"- Coeficientes de M0 en el desarrollo local: intercepto = {m0['intercepto']:.4f}, "
            f"coeficiente del HFRS = {m0['coef_hfrs']:.4f} (n = {m0['n']:,}, eventos = {m0['eventos']:,}, "
            f"prevalencia = {m0['prevalencia']:.1%}).",
            f"- AUROC en MIMIC: {auc}. El intervalo es bootstrap percentil de 1,000 réplicas (semilla 42) y se espera que sea ancho.",
            f"- Calibración-en-lo-grande (observado − predicho): {ext['citl']:+.3f}.",
            f"- Pendiente de calibración (recalibración logística de logit(p)): {ext['pendiente']:.2f} (1 = ideal).",
            f"- Razón observado/esperado: {ext['oe']:.2f} "
            f"({int(ext['observado'])} eventos observados, {ext['esperado']:.2f} esperados según M0).",
            "",
            "![Curva ROC de M0 en MIMIC-IV Demo](../figuras/roc_mimic.png)",
            "",
            "![Calibración de M0 en MIMIC-IV Demo](../figuras/calibracion_mimic.png)",
            "",
            "Un AUROC con n tan pequeño no permite concluir que M0 «funciona» o «no funciona» en MIMIC; "
            "solo indica la dirección de la evidencia en esta muestra pública. La pendiente y la razón O/E "
            "también son inestables con pocos grupos de calibración.",
            "",
        ]

    lineas += [
        "## Por qué no se transportan M3 ni XGBoost",
        "",
        "M3 tiene 37 columnas y XGBoost usa las mismas. Varias son específicas de Synthea o exigirían un "
        "mapeo que no está en el repositorio. Con n ≈ 30 tampoco hay potencial para 37 predictores. "
        "M1 (HFRS, edad y sexo) sí es transportable, pero al haber pocos eventos un modelo de "
        "tres parámetros es exploratorio.",
        "",
        "| Variable | Modelo | ¿Disponible en la demo? | Comentario |",
        "|---|---|---|---|",
    ]
    for variable, modelo, disponible, comentario in DISPONIBILIDAD:
        lineas.append(f"| `{variable}` | {modelo} | {disponible} | {comentario} |")

    lineas += [
        "",
        "## Limitaciones",
        "",
        "- La demo tiene 100 pacientes; después de edad, tipo de ingreso y muerte índice queda una muestra pequeña.",
        "- El seguimiento vital es incompleto (`dod` no equivale a un `observation_period`). La pérdida de seguimiento "
        "puede disfrazarse de «sin evento».",
        "- Las fechas están desplazadas; no se pueden interpretar calendarios reales, solo intervalos.",
        "- Los coeficientes de M0 salen de un único ajuste en el desarrollo, no de las predicciones fuera de pliegue "
        "que se reportaron en `docs/modelos.md`.",
        "- No se versionan datos de MIMIC: solo agregados y figuras sin identificadores.",
        "",
    ]
    return "\n".join(lineas)


def _aviso_desarrollo(m0):
    if m0["n"] != N_DESARROLLO_TESIS:
        return (
            f"**Aviso:** el M0 de esta corrida se ajustó con n = {m0['n']:,} "
            f"({m0['eventos']:,} eventos), no con las {N_DESARROLLO_TESIS:,} personas de la tesis. "
            "Los coeficientes, el AUROC transportado, la pendiente y la razón O/E de esta corrida "
            "**no son los resultados de la tesis**. Vuelven a calcularse cuando el script se corre "
            "con los CSV reales de `data/`."
        )
    return ""


def analizar(ruta_mimic, ruta_ed, features, desenlaces, ruta_hfrs=RUTA_HFRS, ruta_gem=RUTA_GEM):
    """Orquesta carga, cohorte, HFRS, M0 y, si hay eventos suficientes, la validación."""
    tabla_puntos = leer_tabla_hfrs(ruta_hfrs)
    mapa_gem = leer_mapa_gem(ruta_gem)
    patients, admissions, diagnoses, edstays = cargar_tablas(ruta_mimic, ruta_ed)

    n_pacientes_demo = int(patients["subject_id"].nunique())
    adm_edad = admissions.merge(
        patients[["subject_id", "anchor_age", "anchor_year"]], on="subject_id", how="left"
    )
    adm_edad["edad_egreso"] = [
        edad_en_fecha(a, y, t)
        for a, y, t in zip(adm_edad["anchor_age"], adm_edad["anchor_year"], adm_edad["dischtime"])
    ]
    mask_65 = adm_edad["edad_egreso"] >= 65
    indice = construir_cohorte(patients, admissions)
    n_muerte_indice = int(indice["muerte_intrahospitalaria"].sum())
    vivos = indice.loc[indice["muerte_intrahospitalaria"] == 0].copy()
    vivos = calcular_desenlaces(vivos, admissions, edstays, patients)
    vivos = calcular_hfrs_cohorte(vivos, admissions, diagnoses, mapa_gem, tabla_puntos)

    ver_indice = diagnoses.groupby("hadm_id")["icd_version"].apply(lambda s: set(int(v) for v in s))
    vers = vivos["hadm_id"].map(ver_indice)
    n_solo_9 = int(vers.apply(lambda v: v == {9} if isinstance(v, set) else False).sum())
    n_solo_10 = int(vers.apply(lambda v: v == {10} if isinstance(v, set) else False).sum())

    analisis = vivos.loc[vivos["seguimiento_completo"] == 1].copy()
    n_evento_incompleto = int(((vivos["seguimiento_completo"] == 0) & (vivos["compuesto"] == 1)).sum())
    conteos = {
        "n_pacientes_demo": n_pacientes_demo,
        "n_ingresos_65": int(mask_65.sum()),
        "n_personas_65": int(adm_edad.loc[mask_65, "subject_id"].nunique()),
        "n_indice": int(len(indice)),
        "n_muerte_indice": n_muerte_indice,
        "n_cohorte": int(len(vivos)),
        "n_indice_solo_icd9": n_solo_9,
        "n_indice_solo_icd10": n_solo_10,
        "n_dx_icd9": int(vivos["n_dx_icd9"].sum()),
        "n_dx_icd10": int(vivos["n_dx_icd10"].sum()),
        "n_dx_icd9_mapeados": int(vivos["n_dx_icd9_mapeados"].sum()),
        "n_muerte": int(vivos["muerte"].sum()),
        "n_reingreso": int(vivos["reingreso"].sum()),
        "n_urgencias": int(vivos["urgencias"].sum()),
        "n_compuesto": int(vivos["compuesto"].sum()),
        "n_completo": int(len(analisis)),
        "n_compuesto_completo": int(analisis["compuesto"].sum()) if len(analisis) else 0,
        "prev_completo": float(analisis["compuesto"].mean()) if len(analisis) else float("nan"),
        "n_evento_incompleto": n_evento_incompleto,
        "motivo_no_validar": "",
    }

    m0 = ajustar_m0(features, desenlaces)
    aviso = _aviso_desarrollo(m0)

    desarrollo = features.merge(desenlaces, on="person_id")
    hfrs_synthea = desarrollo.loc[desarrollo["seguimiento_completo"] == 1, "hfrs"].to_numpy()
    graficar_hfrs_vs_synthea(vivos["hfrs"].to_numpy(), hfrs_synthea, "figuras/hfrs_mimic_vs_synthea.png")

    Path("data").mkdir(exist_ok=True)
    pd.DataFrame(
        [
            {
                "intercepto": m0["intercepto"],
                "coef_hfrs": m0["coef_hfrs"],
                "n": m0["n"],
                "eventos": m0["eventos"],
                "prevalencia": m0["prevalencia"],
            }
        ]
    ).to_csv("data/m0_coeficientes.csv", index=False)

    ext = None
    eventos_ok = conteos["n_compuesto_completo"] >= N_MIN_EVENTOS
    y_ok = len(analisis) >= 2 and analisis["compuesto"].nunique() == 2
    if (not eventos_ok) or (not y_ok) or (not m0["ajustable"]):
        if not m0["ajustable"]:
            motivo = "el M0 no se pudo ajustar en el desarrollo (HFRS o desenlace sin variación)."
        elif not eventos_ok:
            motivo = (
                f"hay {conteos['n_compuesto_completo']} eventos en {conteos['n_completo']} personas "
                f"con seguimiento completo, por debajo del umbral de {N_MIN_EVENTOS}."
            )
        else:
            motivo = "en la muestra de análisis no hay las dos clases del compuesto."
        conteos["motivo_no_validar"] = motivo
    else:
        pred = aplicar_m0(analisis["hfrs"].to_numpy(), m0["intercepto"], m0["coef_hfrs"])
        predichos = {"M0": pred}
        y = analisis["compuesto"].to_numpy(dtype=int)
        ext = metricas_externas(y, predichos)
        graficar_roc(y, predichos, "figuras/roc_mimic.png")
        graficar_calibracion(y, predichos, "figuras/calibracion_mimic.png")

    markdown = construir_informe(conteos, vivos["hfrs"].to_numpy(), hfrs_synthea, m0, ext, aviso)
    resumen = vivos.drop(columns=[c for c in ("subject_id", "hadm_id", "admit_provider_id") if c in vivos.columns])
    return markdown, conteos, m0, ext, resumen


def _mensaje_descarga():
    return (
        "Descarga de las demos (acceso abierto, sin credenciales), desde el directorio home:\n"
        "  mkdir -p ~/datos && cd ~/datos\n"
        "  curl -L --fail -o mimic-iv-clinical-database-demo-2.2.zip "
        "https://physionet.org/content/mimic-iv-demo/get-zip/2.2/\n"
        "  curl -L --fail -o mimic-iv-ed-demo-2.2.zip "
        "https://physionet.org/content/mimic-iv-ed-demo/get-zip/2.2/\n"
        "  mkdir -p mimic-iv-demo mimic-iv-ed-demo\n"
        "  unzip -o mimic-iv-clinical-database-demo-2.2.zip -d mimic-iv-demo\n"
        "  unzip -o mimic-iv-ed-demo-2.2.zip -d mimic-iv-ed-demo\n"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validación externa de M0 (HFRS) en MIMIC-IV Demo. "
        "Los microdatos se leen fuera del repositorio y no se escriben en data/."
    )
    parser.add_argument("--mimic", type=Path, default=RUTA_MIMIC_DEFECTO)
    parser.add_argument("--ed", type=Path, default=RUTA_ED_DEFECTO)
    parser.add_argument("--features", type=Path, default=Path("data/features_cohorte.csv"))
    parser.add_argument("--desenlaces", type=Path, default=Path("data/desenlaces_cohorte.csv"))
    args = parser.parse_args(argv)

    if buscar_archivo(args.mimic, "patients.csv.gz") is None or buscar_archivo(args.ed, "edstays.csv.gz") is None:
        print("No se encontró la demo de MIMIC-IV o la de urgencias.\n", file=sys.stderr)
        print(_mensaje_descarga(), file=sys.stderr)
        return 1

    features = pd.read_csv(args.features)
    desenlaces = pd.read_csv(args.desenlaces)
    markdown, *_ = analizar(args.mimic, args.ed, features, desenlaces)
    Path("docs").mkdir(exist_ok=True)
    Path("docs/validacion_mimic.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
