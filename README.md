# Presentación del c²HFRS (Clinical / Comprehensive Hospital Frailty Risk Score) como herramienta para predecir desenlaces adversos a 90 días en personas mayores egresadas de una hospitalización (HFRS)

Proyecto final (v1.0). Predice el desenlace compuesto a 90 días (muerte, reingreso a hospitalización o visita a urgencias) después del primer egreso hospitalario de personas de 65 años o más, usando el Hospital Frailty Risk Score (HFRS) de Gilbert et al. (2018) como un baseline para generar una herramienta con una mejor capacidad predictiva.

- Desarrollo en una base **sintética** Synthea convertida a OMOP CDM.
- Modelos logísticos anidados (M0-M3), Cox, riesgos competitivos y XGBoost con SHAP.
- Validación externa **exploratoria** de M0 en MIMIC-IV Demo (datos reales desidentificados, acceso abierto, proveniente de un hospital en Boston, EUA).

Documentos principales:

- [`docs/protocolo.md`](docs/protocolo.md): protocolo del estudio (estructura TRIPOD+AI).
- [`MODEL_CARD.md`](MODEL_CARD.md): ficha del modelo (uso previsto, métricas, ética).
- [`docs/limitaciones.md`](docs/limitaciones.md): limitaciones y trabajo futuro.
- [`docs/uso_ia.md`](docs/uso_ia.md): declaración de uso de IA.

**Uso solo para investigación y docencia. No es una herramienta clínica validada en datos reales, que confirmen los hallazgos de los tres modelos anidados.**

## Estructura del repositorio

```
sql/                      Cohorte 1701, HFRS, desenlaces, características y features
src/fragilidad/           Un script por paso del análisis
scripts/                  generar_gem_hfrs.py (extracto ICD-9 → HFRS del GEM CMS 2018)
tests/                    pytest con datos de ejemplo en memoria (no necesitan las bases)
referencias/              Códigos HFRS, puente SNOMED y extracto del GEM
docs/                     Protocolo, resultados por paso, limitaciones y uso de IA
figuras/                  Figuras sin identificadores
data/                     CSV intermedios (no se versionan)
.github/workflows/ci.yml  pytest y gitleaks en cada push
Dockerfile                Imagen con dependencias fijadas; por defecto corre pytest
docker-compose.yml        Servicios "pruebas" y "pipeline" (Podman o Docker)
MODEL_CARD.md             Ficha del modelo
```

## Datos (no incluidos)

Ningún dato entra al repositorio. `data/`, `*.duckdb` y los archivos de MIMIC están en `.gitignore`.

| Base | Uso | Ruta esperada (fuera del repo) | Cómo obtenerla |
|---|---|---|---|
| Synthea → OMOP (`omop_20k.duckdb`) | Desarrollo | `~/s12-omop-cdm-introduccion/omop_20k.duckdb` | Base del curso (100 % sintética) |
| MIMIC-IV Clinical Database Demo v2.2 | Validación externa | `~/datos/mimic-iv-demo` | PhysioNet, acceso abierto sin credenciales |
| MIMIC-IV-ED Demo v2.2 | Urgencias en la validación | `~/datos/mimic-iv-ed-demo` | PhysioNet, acceso abierto sin credenciales |
| GEM ICD-9 → ICD-10 de CMS (2018) | Traducción de diagnósticos ICD-9 | Fuera del repo; solo se versiona el extracto `referencias/hfrs_icd9_gem.csv` | cms.gov, dominio público |

## Cómo reproducir

### 1. Entorno

```bash
cd ~/fragilidad-hfrs-90d
source ~/venv_go/bin/activate
pip install -r requirements.txt
```

### 2. Pruebas

No necesitan ninguna base:

```bash
PYTHONPATH=src python -m pytest -v
```

### 3. Análisis, en orden

Todos los scripts se corren desde la raíz del repositorio, porque las rutas `sql/`, `referencias/`, `data/`, `docs/` y `figuras/` son relativas.

```bash
DB=~/s12-omop-cdm-introduccion/omop_20k.duckdb

# Cohorte, diagrama de flujo, HFRS, desenlaces y Tabla 1
PYTHONPATH=src python src/fragilidad/atricion.py $DB         # docs/atricion.md
PYTHONPATH=src python src/fragilidad/diagrama_flujo.py $DB   # diagrama de flujo de inclusión
PYTHONPATH=src python src/fragilidad/hfrs.py $DB             # data/hfrs_cohorte.csv
PYTHONPATH=src python src/fragilidad/desenlaces.py $DB       # data/desenlaces_cohorte.csv
PYTHONPATH=src python src/fragilidad/tabla1.py $DB           # docs/tabla1.md

# Kaplan-Meier, log-rank y Cox de muerte
PYTHONPATH=src python src/fragilidad/supervivencia.py $DB    # docs/supervivencia.md, figuras/km_*.png

# Matriz de 37 features pre-índice
PYTHONPATH=src python src/fragilidad/features.py $DB         # data/features_cohorte.csv

# Incidencia acumulada (Aalen-Johansen) y prueba de Gray
PYTHONPATH=src python src/fragilidad/riesgos_competitivos.py # docs/riesgos_competitivos.md, figuras/cif_*.png

# Cox y logística univariados
PYTHONPATH=src python src/fragilidad/univariado.py           # docs/univariado.md, figuras/forest_univariado.png

# Modelos anidados M0-M3 y Cox multivariable
PYTHONPATH=src python src/fragilidad/modelos.py              # docs/modelos.md, figuras/roc_modelos.png, calibracion_modelos.png

# XGBoost y SHAP
PYTHONPATH=src python src/fragilidad/xgb_shap.py             # docs/xgb_shap.md, figuras/roc_xgb.png, calibracion_xgb.png, shap_*.png

# Validación externa de M0 en MIMIC-IV Demo
PYTHONPATH=src python src/fragilidad/validacion_mimic.py \
  --mimic ~/datos/mimic-iv-demo --ed ~/datos/mimic-iv-ed-demo # docs/validacion_mimic.md, figuras/*_mimic*.png
```

El extracto `referencias/hfrs_icd9_gem.csv` ya está versionado. Solo hay que regenerarlo con `scripts/generar_gem_hfrs.py` si cambia la lista de códigos del HFRS.

### 4. Con contenedores (Podman en Fedora/Linux, o Docker)

```bash
podman-compose build
podman-compose run --rm pruebas     # pytest
podman-compose run --rm pipeline    # análisis completo
```

El servicio `pipeline` monta las bases en solo lectura (`:ro`) desde fuera del repositorio, con etiquetas SELinux (`:z`/`:Z`). Las rutas se cambian con las variables `OMOP_DB`, `MIMIC_DIR` y `MIMIC_ED_DIR`.

## Resultados principales

**Cohorte 1701:** 11,745 primeros egresos a los 65 años o más, de los cuales se utilizan  **5,515 personas** (atrición en [`docs/protocolo.md`](docs/protocolo.md)). Logística: 5,372 con seguimiento completo (2,009 eventos, 37.4 %). Cox: 5,494 (2,051 eventos).

**HFRS:** bajo (<5) 94.4 %, intermedio (5 a 15) 5.4 %, alto (>15) 10 personas (0.2 %); mediana 0.6.

**Desenlaces a 90 días (n = 5,515):** muerte 6.7 %, reingreso 16.5 %, urgencias 19.6 %, compuesto 37.2 %.

**Modelos del compuesto (validación cruzada de 5 pliegues, n = 5,372):**

| Modelo | Variables | AUROC [IC 95 %] | AUPRC | Pendiente de calibración |
|---|---:|---|---:|---:|
| M0: HFRS | 1 | 0.600 | — | 0.99 |
| M1: + edad y sexo | 3 | 0.592 | — | 0.96 |
| M2: + comorbilidades y fármacos | 15 | 0.689 | — | 0.97 |
| M3: + laboratorios, utilización y estancia | 37 | 0.734 | 0.672 | 0.90 |
| XGBoost (variables de M3) | 37 | 0.810 [0.798-0.823] | 0.750 | 1.03 |

- XGBoost supera a M3 en ΔAUROC +0.076 [0.065-0.087].
- En el Cox de M3, el HFRS ajustado da un HR de 1.03 [1.02-1.05] por punto.
- Las urgencias a 90 días aumentan con el HFRS (Gray p < 0.001).

**Validación externa exploratoria de M0 (MIMIC-IV Demo, 27 personas, 14 eventos):** AUROC 0.703 [0.488-0.894], CITL −0.091, pendiente 0.83, O/E 0.85. El IC cruza 0.5.

El detalle de cada paso está en `docs/`: [`atricion.md`](docs/atricion.md), [`tabla1.md`](docs/tabla1.md), [`supervivencia.md`](docs/supervivencia.md), [`riesgos_competitivos.md`](docs/riesgos_competitivos.md), [`univariado.md`](docs/univariado.md), [`modelos.md`](docs/modelos.md), [`xgb_shap.md`](docs/xgb_shap.md) y [`validacion_mimic.md`](docs/validacion_mimic.md).

## Figuras

| Figura | Archivo |
|---|---|
| Kaplan-Meier de muerte por categoría de HFRS y por terciles | [`km_muerte_hfrs.png`](figuras/km_muerte_hfrs.png), [`km_muerte_terciles.png`](figuras/km_muerte_terciles.png) |
| Incidencia acumulada de reingreso y urgencias | [`cif_reingreso.png`](figuras/cif_reingreso.png), [`cif_urgencias.png`](figuras/cif_urgencias.png) |
| Forest plot univariado | [`forest_univariado.png`](figuras/forest_univariado.png) |
| ROC y calibración de M0-M3 | [`roc_modelos.png`](figuras/roc_modelos.png), [`calibracion_modelos.png`](figuras/calibracion_modelos.png) |
| ROC y calibración de XGBoost | [`roc_xgb.png`](figuras/roc_xgb.png), [`calibracion_xgb.png`](figuras/calibracion_xgb.png) |
| SHAP (beeswarm, importancia y un caso sin identificadores) | [`shap_beeswarm.png`](figuras/shap_beeswarm.png), [`shap_importancia.png`](figuras/shap_importancia.png), [`shap_paciente.png`](figuras/shap_paciente.png) |
| HFRS en MIMIC frente a Synthea | [`hfrs_mimic_vs_synthea.png`](figuras/hfrs_mimic_vs_synthea.png) |
| ROC y calibración de M0 en MIMIC | [`roc_mimic.png`](figuras/roc_mimic.png), [`calibracion_mimic.png`](figuras/calibracion_mimic.png) |
| Diagrama de flujo de inclusión (cohorte 1701) | [`flujo_cohorte.png`](figuras/flujo_cohorte.png) |

## Limitaciones

- Datos de desarrollo sintéticos, con HFRS comprimido y si se presentan algunos artefactos asociados al uso de datos sintéticos de Synthea.
- El supuesto de riesgos proporcionales se viola en 17 de 37 variables del Cox de M3.
- Los faltantes de laboratorio son informativos.
- SHAP no es causal.
- La validación en MIMIC es exploratoria (n = 27, un solo hospital) y el GEM ICD-9 → ICD-10 añade error de medición.

Detalle en [`docs/limitaciones.md`](docs/limitaciones.md).

## Privacidad y seguridad

- Cero credenciales y cero datos identificables en el repositorio.
- Sin microdatos: solo agregados y figuras sin identificadores.
- gitleaks antes de cada push (local con Podman y en CI).

## Licencias

- **Código y documentos:** repositorio académico privado del proyecto final.
- **MIMIC-IV Clinical Database Demo v2.2 y MIMIC-IV-ED Demo v2.2:** Open Database License (ODbL) v1.0, PhysioNet. 
- **GEM 2018 de CMS:** dominio público (proveniente del gobierno de EE. UU.).
- **Códigos del HFRS:** Gilbert et al., *Lancet* 2018;391:1775-82, material suplementario.
- **Synthea:** generador de código abierto (Apache 2.0). 

## Declaración de uso de IA

Se usó un asistente de inteligencia artificial (Grok Bot) como tutor para explicar código y revisar resultados. Yo ejecuté y verifiqué cada paso. La declaración completa está en [`docs/uso_ia.md`](docs/uso_ia.md).
