# Diccionario de datos

Los CSV de resultados viven en `data/`. Las columnas de abajo son las que producen los scripts de `src/fragilidad/` a partir de la cohorte. 

## `data/hfrs_cohorte.csv` (`hfrs.py`, `sql/03_hfrs.sql`)

| Columna | Tipo | Descripción |
|---|---|---|
| `person_id` | entero | Identificador de la persona en OMOP (es el `subject_id` de la cohorte). |
| `fecha_indice` | fecha | Fecha de egreso de la hospitalización índice (`cohort_start_date`). |
| `hfrs` | decimal (1 dígito) | Hospital Frailty Risk Score de Gilbert et al. (2018). Suma de los puntos de los códigos CIE-10 presentes en los 730 días previos al egreso, incluyendo el día índice. Incluye el ajuste F00 (7.1 puntos) en quien tiene G30. |
| `hfrs_sin_f00` | decimal (1 dígito) | Mismo puntaje, sin el ajuste F00. Análisis de sensibilidad. |
| `hfrs_sin_social` | decimal (1 dígito) | Mismo puntaje, sin los códigos Z60 ni Z73. Análisis de sensibilidad, porque en Synthea esos códigos salen de «Social isolation» y «Stress». |
| `categoria` | texto | Categoría de Gilbert 2018: `<5` (bajo), `5-15` (intermedio; incluye el 15) o `>15` (alto). Se calcula sobre `hfrs`. |

## `data/desenlaces_cohorte.csv` (`desenlaces.py`, `sql/04_desenlaces.sql`)

| Columna | Tipo | Descripción |
|---|---|---|
| `person_id` | entero | Identificador de la persona en OMOP. |
| `dias_seguimiento` | entero | Días entre el egreso y el fin de observación de la cohorte (`cohort_end_date`). El máximo planeado es 90. |
| `dias_muerte` | entero o vacío | Días desde el egreso hasta la muerte en los días 1 a 90. Vacío si no hubo muerte en esa ventana. El día 0 no cuenta. |
| `dias_reingreso` | entero o vacío | Días hasta la primera hospitalización (`visit_concept_id` 9201) en los días 1 a 90. |
| `dias_urgencias` | entero o vacío | Días hasta la primera visita a urgencias (`visit_concept_id` 9203) en los días 1 a 90. |
| `muerte` | 0/1 | 1 si `dias_muerte` no está vacío. |
| `reingreso` | 0/1 | 1 si `dias_reingreso` no está vacío. |
| `urgencias` | 0/1 | 1 si `dias_urgencias` no está vacío. |
| `compuesto` | 0/1 | 1 si ocurrió al menos uno de los tres eventos. |
| `dias_compuesto` | entero o vacío | Menor de los tres tiempos de evento. Vacío si no hubo ninguno. |
| `seguimiento_completo` | 0/1 | 1 si la persona fue observada al menos 90 días o murió dentro de esos 90 días. 0 significa seguimiento incompleto (se censura en supervivencia y se excluye de la Tabla 1). |

## Características basales (`sql/05_caracteristicas.sql`, usadas en `tabla1.py`)

| Columna | Tipo | Descripción |
|---|---|---|
| `edad` | entero | Años cumplidos al egreso índice. |
| `hombre` | 0/1 | 1 si `gender_concept_id` = 8507. |
| `dm2_prev` | 0/1 | Diabetes tipo 2 (concepto 201826 y descendientes) registrada antes del día índice, ventana (-∞, -1]. |
| `ic_prev` | 0/1 | Insuficiencia cardiaca (316139 y descendientes), misma ventana. |
| `erc_prev` | 0/1 | Enfermedad renal crónica (46271022 y descendientes), misma ventana. |
| `demencia_prev` | 0/1 | Demencia (4182210 y descendientes), misma ventana. |
| `creatinina` | decimal o vacío | Último valor de creatinina sérica (conceptos 3016723 y 3051825) en los días [-365, 0], tal como viene en `value_as_number`. |
| `albumina` | decimal o vacío | Último valor de albúmina (3024561) en [-365, 0]. |
| `tfge` | decimal o vacío | Último valor de tasa de filtración glomerular estimada (46236952) en [-365, 0]. |
| `hemoglobina` | decimal o vacío | Último valor de hemoglobina (3000963) en [-365, 0]. |

## Variables de supervivencia (`supervivencia.py`)

| Columna | Tipo | Descripción |
|---|---|---|
| `evento` | 0/1 | 1 si murió en los días 1 a 90 (igual a `muerte`). |
| `tiempo` | entero | `dias_muerte` si murió; si no, el menor entre `dias_seguimiento` y 90 (censura). |
| `tercil` | texto | Tercil del HFRS en la muestra (`T1`, `T2`, `T3`) con `pd.qcut(..., duplicates="drop")`. Cortes observados: 0.0, 0.6, 2.4 y 19.1. |
