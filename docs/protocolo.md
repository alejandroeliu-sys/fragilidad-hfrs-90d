# Protocolo del estudio

**Título:** Desarrollo del modelo c²HFRS (Clinical / Comprehensive Hospital Frailty RIsk Score) sobre Fragilidad hospitalaria (HFRS) y desenlaces adversos a 90 días tras el egreso en personas de 65 años o más: desarrollo en datos sintéticos (Synthea a OMOP) y validación externa exploratoria en MIMIC-IV Demo.

El documento sigue la estructura de TRIPOD+AI. Es un estudio de desarrollo con validación interna por validación cruzada (TRIPOD tipo 1b) y una validación externa exploratoria en datos independientes de un hospital real (tipo 3, solo para M0).

## 1. Objetivo

Estimar la capacidad predictiva del c²HFRS.

Preguntas:

1. ¿El HFRS solo (M0) puede discriminar el desenlace compuesto?
2. ¿Cuánto agregan la demografía (M1), las comorbilidades y los fármacos (M2), y los laboratorios, la utilización previa y la estancia índice en el modelo M3?
3. ¿Un modelo no lineal (XGBoost) con las mismas variables de M3 mejora la discriminación y la calibración?
4. ¿Se conserva la discriminación del modelo anidado en un hospital real (MIMIC-IV Demo)?

Uso previsto: investigación y docencia. No es una herramienta clínica validada en datos reales con un adecuado tamaño de la muestra.

## 2. Fuentes de datos

| Uso | Fuente | Versión | Licencia | Dónde vive |
|---|---|---|---|---|
| Desarrollo | Synthea convertido a OMOP CDM (`omop_20k.duckdb`) | Base del curso | Datos 100 % sintéticos | Fuera del repositorio |
| Validación externa exploratoria | MIMIC-IV Clinical Database Demo | v2.2 | ODbL v1.0 (PhysioNet, acceso abierto) | `~/datos/mimic-iv-demo` (fuera del repositorio) |
| Visitas a urgencias en la validación | MIMIC-IV-ED Demo | v2.2 | ODbL v1.0 (PhysioNet, acceso abierto) | `~/datos/mimic-iv-ed-demo` (fuera del repositorio) |
| Traducción ICD-9 a ICD-10 | General Equivalence Mappings (GEM) de CMS | 2018 | Dominio público | Solo el extracto `referencias/hfrs_icd9_gem.csv` |
| Códigos y puntos del HFRS | Material suplementario de Gilbert et al. (2018) | 109 códigos | Artículo de acceso abierto | `referencias/hfrs_codigos.csv` |

Ningún dato entra al repositorio. Solo se versionan agregados, figuras sin identificadores y listas de referencia.

## 3. Población y cohorte (cohorte 1701)

- **Fecha índice (día 0):** primer egreso hospitalario (visita 9201) a los 65 años o más.
- **Criterios de inclusión:** 730 días de observación previa; sin hospitalización en los 30 días previos (lavado); 2 o más visitas ambulatorias en 365 días; creatinina, albúmina sérica y tasa de filtración glomerular medidas en 365 días; multimorbilidad (2 o más diagnósticos en 730 días).
- **Criterios de exclusión:** cáncer maligno en 365 días; muerte el día del egreso o antes (debido a que puede corresponder a un artefacto de Synthea en una cohorte de egresos).

### Atrición

| Paso | n | Perdidos |
|---|---:|---:|
| Primer egreso hospitalario a los 65 años o más | 11,745 | 0 |
| + 730 días de observación previa | 11,745 | 0 |
| + sin hospitalización en los 30 días previos | 11,708 | 37 |
| + 2 visitas ambulatorias o más en 365 días | 9,258 | 2,450 |
| + creatinina en 365 días | 7,790 | 1,468 |
| + albúmina sérica en 365 días | 6,352 | 1,438 |
| + tasa de filtración glomerular en 365 días | 6,351 | 1 |
| + multimorbilidad (2 dx o más en 730 días) | 6,334 | 17 |
| − cáncer maligno en 365 días | 5,885 | 449 |
| − muerte el día del egreso o antes | **5,515** | 370 |

### Conjuntos analíticos

- **Logística (M0-M3, XGBoost):** 5,372 personas con seguimiento completo a 90 días; 2,009 eventos (prevalencia 37.4 %). Las 143 personas con seguimiento incompleto no fueron incluidos porque su desenlace no se conocio.
- **Cox:** 5,494 personas con tiempo de observación mayor que 0; 2,051 eventos. La censura es `min(dias_seguimiento, 90)`.

## 4. Exposición principal: HFRS

- 109 códigos ICD-10 de 3 caracteres con sus puntos.
- Ventana: diagnósticos en los 730 días hasta el egreso índice, inclusive ([−730, 0]); incluye la hospitalización índice.
- Traducción en Synthea: SNOMED a ICD10CM con la relación `Mapped from` del vocabulario OMOP, usando los primeros 3 caracteres.
- **Ajuste F00:** F00 (demencia en la enfermedad de Alzheimer, 7.1 puntos) no existe en ICD10CM. Se asigna a quien tiene G30. El puntaje sin ese ajuste se guarda en `hfrs_sin_f00`.
- **Puente manual:** 9 conceptos SNOMED frecuentes en Synthea sin traducción automática (`referencias/puente_snomed_hfrs.csv`).
- **Sensibilidad:** `hfrs_sin_social` quita Z60 y Z73, que en Synthea salen de «Social isolation» y «Stress».
- Categorías de Gilbert: bajo (<5), intermedio (5 a 15), alto (>15). También se usa el HFRS continuo (por punto) y terciles de la muestra.

Distribución en la cohorte (n = 5,515): bajo 5,208 (94.4 %), intermedio 297 (5.4 %), alto 10 (0.2 %); mediana 0.6, máximo 19.1.

## 5. Desenlaces

Todos se miden en los días 1 a 90 de calendario después del egreso; el día 0 no cuenta.

- **Principal: compuesto** de muerte, reingreso (visita 9201) o visita a urgencias (visita 9203). 2,051 personas (37.2 % de 5,515).
- **Secundarios por separado:** muerte 369 (6.7 %), reingreso 910 (16.5 %), urgencias 1,082 (19.6 %).
- **Seguimiento completo:** observación hasta el día 90 o muerte observada. Seguimiento incompleto: 143 personas (2.6 %).

## 6. Predictores

37 variables pre-índice (`docs/features.md`), agrupadas en bloques:

- **M0:** HFRS (1 variable).
- **M1:** M0 + edad y sexo (3).
- **M2:** M1 + comorbilidades diagnosticadas (diabetes tipo 2, insuficiencia cardiaca, enfermedad renal crónica, demencia, cardiopatía isquémica, hipertensión, anemia), número de ingredientes en 365 y 30 días, y diabetes, hipertensión e insuficiencia cardiaca inferidas por fármacos (15).
- **M3:** M2 + laboratorios (último valor, número de mediciones, pendiente y desviación estándar), presión arterial sistólica, IMC, utilización previa (visitas ambulatorias, hospitalizaciones y urgencias en 365 días), estancia índice e indicadores de faltante (37).

Ventanas: comorbilidades (−∞, −1]; fármacos, laboratorios, signos y visitas [−365, −1]; HFRS [−730, 0]. Los indicadores `albumina_falta`, `creatinina_falta` y `tfge_falta` se excluyen de M1-M3 porque en el análisis univariado fueron no concluyentes.

## 7. Análisis estadístico

### 7.1 Descriptivo y supervivencia

- Tabla 1 por muerte a 90 días: Mann-Whitney, chi cuadrada y Fisher (`docs/tabla1.md`).
- Kaplan-Meier de muerte por categoría de HFRS y por terciles, con log-rank; Cox con HFRS continuo (`docs/supervivencia.md`).

### 7.2 Riesgos competitivos

Para reingreso y urgencias, la muerte es un riesgo competitivo. Se estima la incidencia acumulada de Aalen-Johansen y se compara entre grupos con la prueba de Gray (rho = 0), validada contra `cmprsk::cuminc` de R (`docs/riesgos_competitivos.md`).

### 7.3 Univariado

Cox y logística univariados de cada predictor sobre el compuesto (`docs/univariado.md`).

### 7.4 Modelos anidados M0-M3

- Logística sin penalización sobre el compuesto binario.
- Validación cruzada estratificada de 5 pliegues (semilla 42) con predicciones fuera de pliegue.
- Imputación por mediana dentro de cada pliegue (solo con el entrenamiento); estandarización con media y DE del entrenamiento solo para que converja.
- Cox multivariable de M3 en unidades naturales, con la prueba de Schoenfeld para riesgos proporcionales.

### 7.5 XGBoost y SHAP

- Mismas 37 variables y mismos pliegues que M3. Faltantes nativos (sin imputar) y sin estandarizar.
- Hiperparámetros fijos, sin búsqueda: `n_estimators=300`, `max_depth=3`, `learning_rate=0.05`, `subsample=0.8`, `colsample_bytree=0.8`, `min_child_weight=5`, `reg_lambda=1.0`, `random_state=42`.
- SHAP con TreeExplainer: comprobación de aditividad, gráficos beeswarm, de importancia y de un paciente (waterfall) sin identificadores.

### 7.6 Métricas

- Discriminación: AUROC y AUPRC (la AUPRC de referencia es la prevalencia, 0.374).
- Calibración: pendiente de calibración (1 = ideal), calibración-en-lo-grande (CITL, observado − predicho; 0 = ideal) y curvas de calibración.
- Incertidumbre: IC 95 % bootstrap percentil, 1,000 réplicas (semilla 42). Las diferencias de AUROC frente a M0 y M3 son pareadas (mismas réplicas).

## 8. Validación externa exploratoria (MIMIC-IV Demo)

- **Modelo transportado:** solo M0. Se ajusta una vez en Synthea (5,372 personas con seguimiento completo), en unidades naturales: intercepto −0.737 y coeficiente del HFRS 0.116 por punto. Se aplica sin cambios en MIMIC (sin recalibrar ni reajustar).
- **Cohorte:** edad = `anchor_age` + (año del egreso − `anchor_year`). El índice es el primer egreso a los 65 años o más en ingresos de tipo EW EMER., URGENT, ELECTIVE, DIRECT EMER., SURGICAL SAME DAY ADMISSION u OBSERVATION ADMIT. Se excluyen las muertes intrahospitalarias del índice.
- **Desenlaces:** días 1-90; muerte (`dod`), reingreso (`admissions`) y urgencias (`edstays` de la demo de ED). El seguimiento es completo si hay evidencia en el día 90 o después, o una muerte observada.
- **HFRS:** ventana de ingresos con `dischtime` en [índice − 730, índice]. Los diagnósticos ICD-10 se usan con 3 caracteres. Los ICD-9 se traducen con el GEM CMS 2018 (filas con bandera *no map* = 0); ocho códigos HFRS no tienen origen ICD-9 (F00, J22, R02, R54, U80, X59, Y95, Z50), y F00 se sigue asignando por G30.
- **Umbral preespecificado:** se reporta la validación solo si hay 10 eventos o más.
- **Métricas:** AUROC con IC bootstrap, CITL, pendiente de calibración y razón observado/esperado (O/E).
- **Por qué no M3 ni XGBoost:** varias de sus 37 variables son propias de Synthea o exigirían mapeos que no están implementados, y con n = 27 no hay potencia para 37 predictores.

## 9. Resultados principales

### Riesgos competitivos (Gray)

- Urgencias por categoría de HFRS: Gray 16.39, p < 0.001 (5-15: 27.6 % frente a <5: 19.4 %). Por terciles: T1 10.9 %, T2 28.3 %, T3 31.0 %.
- Reingreso por categoría: p = 0.090. Por terciles, p < 0.001 pero inverso (T1 20.7 % frente a T3 11.4 %, con muerte del 13.3 % en T3), lo que se interpreta como competencia por la muerte.

### Univariado (compuesto)

HFRS: HR 1.08 por punto (OR 1.12). Edad HR 1.014; demencia 1.99; enfermedad renal crónica 1.58; diabetes tipo 2 1.42; hospitalizaciones en 365 días 1.14.

### Modelos (validación cruzada, n = 5,372)

| Modelo | AUROC | AUPRC | Pendiente de calibración |
|---|---:|---:|---:|
| M0 (HFRS) | 0.600 | — | 0.99 |
| M1 (+ edad, sexo) | 0.592 | — | 0.96 |
| M2 (+ comorbilidades, fármacos) | 0.689 | — | 0.97 |
| M3 (+ laboratorios, utilización, estancia) | 0.734 | 0.672 | 0.90 |
| XGBoost (variables de M3) | 0.810 [0.798-0.823] | 0.750 | 1.03 |

- XGBoost frente a M3: ΔAUROC +0.076 [0.065-0.087].
- Cox M3: C-index aparente 0.695; HFRS ajustado HR 1.03 [1.02-1.05] por punto; insuficiencia cardiaca 1.98; enfermedad renal crónica 1.45; demencia 1.21. Se viola el supuesto de riesgos proporcionales en 17 de 37 variables.
- SHAP: las variables más importantes son `n_urgencias_365`, `estancia_indice_dias` (relación no lineal) y `n_ingredientes_30`. El HFRS queda en el 7.º lugar, con una correlación de 0.77 entre su valor y su valor SHAP.

Las cifras con IC completos están en `docs/modelos.md` y `docs/xgb_shap.md`.

### Validación externa (MIMIC-IV Demo)

- Cohorte postegreso: 45 personas; 27 con seguimiento completo y 14 eventos (51.9 %).
- HFRS en MIMIC: mediana 7.6 (P25 3.2, P75 12.2, máximo 25.3), frente a 0.6 en Synthea.
- M0 transportado: AUROC 0.703 [0.488-0.894]; CITL −0.091; pendiente 0.83; O/E 0.85.

## 10. Datos faltantes

- Laboratorios, signos vitales e IMC: indicador `_falta` (0/1) más imputación por mediana dentro del pliegue en la logística.
- El faltante es debido al uso de datos sinteticos en Synthea (por ejemplo, falta la hemoglobina en 470 sobrevivientes y en 4 muertes).

## 11. Reproducibilidad

- Código en `src/fragilidad/`, SQL en `sql/`, pruebas en `tests/` (pytest; CI con GitHub Actions y gitleaks).
- Versiones fijadas en `requirements.txt`; `Dockerfile` y `docker-compose.yml` (Podman o Docker).
- Semilla 42 en pliegues, bootstrap y XGBoost.

## 12. Ética y privacidad

- Desarrollo con datos 100 % sintéticos.
- MIMIC-IV Demo está desidentificada según HIPAA y es de acceso abierto (ODbL); sus datos no se versionan.
- No hay identificadores de persona en figuras ni documentos, y no hay credenciales en el repositorio (gitleaks antes de cada push).

## 13. Limitaciones

Ver [`limitaciones.md`](limitaciones.md).

## Referencias

- Gilbert T, Neuburger J, Kraindler J, et al. Development and validation of a Hospital Frailty Risk Score focusing on older people in acute care settings using electronic hospital records. *Lancet* 2018;391:1775-82.
- Collins GS, Moons KGM, Dhiman P, et al. TRIPOD+AI statement. *BMJ* 2024;385:e078378.
- Johnson A, Bulgarelli L, Pollard T, et al. MIMIC-IV Clinical Database Demo (v2.2). PhysioNet, 2023.
- Johnson A, Bulgarelli L, Pollard T, et al. MIMIC-IV-ED Demo (v2.2). PhysioNet, 2023.
- Goldberger AL, et al. PhysioBank, PhysioToolkit, and PhysioNet. *Circulation* 2000;101:e215-20.
- Centers for Medicare & Medicaid Services. 2018 ICD-10-CM General Equivalence Mappings.
- Gray RJ. A class of K-sample tests for comparing the cumulative incidence of a competing risk. *Ann Stat* 1988;16:1141-54.
- Lundberg SM, Lee SI. A unified approach to interpreting model predictions. *NeurIPS* 2017.
- Mitchell M, Wu S, Zaldivar A, et al. Model cards for model reporting. *FAT\** 2019.
