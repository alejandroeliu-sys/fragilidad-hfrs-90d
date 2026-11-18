# Matriz de features pre-índice

`src/fragilidad/features.py` corre `sql/02_cohorte.sql`, `sql/03_hfrs.sql` y `sql/06_features.sql` y guarda `data/features_cohorte.csv` . Hay una fila por persona de la cohorte (5,515 personas, 43 columnas). Se corre desde la raíz del repo:

```bash
PYTHONPATH=src python src/fragilidad/features.py ~/s12-omop-cdm-introduccion/omop_20k.duckdb
```

## Ventanas (día 0 = egreso = `cohort_start_date`)

| Bloque | Ventana | Motivo |
|---|---|---|
| Comorbilidades diagnosticadas | (-∞, -1] | Todo el registro previo; el día 0 se excluye. |
| Fármacos, laboratorios, signos y visitas | [-365, -1] | Último año; el día 0 se excluye para no usar datos del mismo día del egreso. |
| HFRS | [-730, 0] | Definición de Gilbert 2018: incluye los diagnósticos de la hospitalización índice. |
| Estancia índice | Hospitalización que termina el día 0 | Se conoce al momento del egreso. |

Los laboratorios usan [-365, -1], no [-365, 0] como `sql/05_caracteristicas.sql` (Tabla 1). 

## Columnas

| Columna | Tipo | Ventana | Descripción |
|---|---|---|---|
| `person_id` | entero | — | Identificador OMOP. No es feature. |
| `fecha_indice` | fecha | día 0 | Fecha de egreso. No es feature; sirve para el corte temporal entrenamiento/prueba. |
| `edad` | entero | día 0 | Años cumplidos en la fecha índice (mismo cálculo que `sql/05`). |
| `sexo_masc` | 0/1 | — | 1 si `gender_concept_id` = 8507. |
| `obs_previa_dias` | entero o vacío | hasta día 0 | Días desde el inicio del periodo de observación que contiene la fecha índice. |
| `dm2_dx` | 0/1 | (-∞, -1] | Diabetes tipo 2 (201826 y descendientes). |
| `ic_dx` | 0/1 | (-∞, -1] | Insuficiencia cardiaca (316139). |
| `erc_dx` | 0/1 | (-∞, -1] | Enfermedad renal crónica (46271022). |
| `demencia_dx` | 0/1 | (-∞, -1] | Demencia (4182210). |
| `cardiop_isq_dx` | 0/1 | (-∞, -1] | Cardiopatía isquémica (4185932). |
| `hta_dx` | 0/1 | (-∞, -1] | Hipertensión (320128). |
| `anemia_dx` | 0/1 | (-∞, -1] | Anemia (439777). |
| `n_ingredientes_365` | entero | [-365, -1] | Ingredientes distintos recetados. |
| `n_ingredientes_30` | entero | [-30, -1] | Ingredientes distintos en el último mes. |
| `dm_inferida` | 0/1 | [-365, -1] | Metformina o insulina en ≥ 2 fechas distintas. |
| `hta_inferida` | 0/1 | [-365, -1] | Lisinopril, HCTZ, amlodipino o losartán en ≥ 2 fechas. |
| `ic_inferida` | 0/1 | [-365, -1] | Furosemida en ≥ 2 fechas y carvedilol o metoprolol al menos una vez. |
| `albumina_ultima` | decimal o vacío | [-365, -1] | Última albúmina (g/dL, 3024561). |
| `albumina_n` | entero | [-365, -1] | Número de mediciones de albúmina. |
| `albumina_pendiente` | decimal o vacío | [-365, -1] | Cambio por año (regresión lineal); vacío si hay menos de 3 días con medición. |
| `albumina_de` | decimal o vacío | [-365, -1] | Desviación estándar; vacía si hay menos de 3 días con medición. |
| `creatinina_ultima` | decimal o vacío | [-365, -1] | Última creatinina (mg/dL; 3016723 o 3051825). |
| `creatinina_n` | entero | [-365, -1] | Número de mediciones de creatinina. |
| `creatinina_pendiente` | decimal o vacío | [-365, -1] | Cambio por año; misma regla de 3 días. |
| `urea_ultima` | decimal o vacío | [-365, -1] | Última urea/BUN (mg/dL, 3004295). |
| `urea_n` | entero | [-365, -1] | Número de mediciones de urea. |
| `urea_pendiente` | decimal o vacío | [-365, -1] | Cambio por año; misma regla de 3 días. |
| `hemoglobina_ultima` | decimal o vacío | [-365, -1] | Última hemoglobina (g/dL, 3000963). |
| `tfge_ultima` | decimal o vacío | [-365, -1] | Última TFGe (mL/min/1.73 m², 46236952). |
| `pas_ultima` | decimal o vacío | [-365, -1] | Última presión sistólica (mmHg, 3004249). |
| `imc_ultimo` | decimal o vacío | [-365, -1] | Último IMC (kg/m², 3038553). |
| `n_ambulatorias_365` | entero | [-365, -1] | Visitas ambulatorias (9202). |
| `n_hosp_365` | entero | [-365, -1] | Hospitalizaciones previas (9201) que terminaron antes del día 0; no cuenta la estancia índice. |
| `n_urgencias_365` | entero | [-365, -1] | Visitas a urgencias (9203). |
| `estancia_indice_dias` | entero o vacío | estancia índice | Días entre ingreso y egreso de la hospitalización índice. |
| `hfrs` | decimal (1 dígito) | [-730, 0] | Hospital Frailty Risk Score (sale de `sql/03_hfrs.sql`). |
| `albumina_falta`, `creatinina_falta`, `urea_falta`, `hemoglobina_falta`, `tfge_falta`, `pas_falta`, `imc_falta` | 0/1 | [-365, -1] | 1 si la última medición correspondiente está vacía. |

## Faltantes

En la cohorte real faltan: albúmina 8.4 %, creatinina 0.1 %, urea 10.6 %, hemoglobina 11.0 %, TFGe 8.3 %, presión sistólica 1.3 % e IMC 1.4 %. Las pendientes faltan más (25 % a 57 %) porque exigen mediciones en 3 días distintos.

Los valores sin medición se dejan vacíos (NULL); no se imputan en el SQL. Los conteos (`_n`, `n_`) y las comorbilidades valen 0 cuando no hay registro. Las pendientes y desviaciones vacías no llevan indicador propio, porque se deducen de `_n`.

## NOTAS: 

- No incluye ninguna columna de desenlace.
- La cohorte sale de la tabla temporal `cohorte` (`sql/02_cohorte.sql`) y no se exige tener 90 días de seguimiento. 
- La edad usa años cumplidos, como `sql/05`, en lugar de `FLOOR(días / 365.25)`.
- Las comorbilidades agregan el propio concepto ancestro.
- La creatinina junta los conceptos 3016723 y 3051825.
- Se agregan `hemoglobina_ultima`, `tfge_ultima`, `hfrs` y los 7 indicadores `_falta`.
