# Model card: predicción de desenlaces adversos a 90 días tras el egreso (HFRS, M0-M3 y XGBoost)

## Detalles del modelo

- **Autor:** alejandroeliu-sys, proyecto final del curso (repositorio `fragilidad-hfrs-90d`).
- **Fecha y versión:** noviembre de 2026, v1.0.
- **Tipo de modelos:**
  - M0-M3: regresión logística sin penalización, anidada por bloques de variables (1, 3, 15 y 37 predictores).
  - Cox multivariable con las variables de M3 (para HR ajustados, no para predecir, obteniendo un total de 37 variables incluidas en este modelo).
  - XGBoost (árboles de gradiente) con las 37 variables de M3 e hiperparámetros fijos: `n_estimators=300`, `max_depth=3`, `learning_rate=0.05`, `subsample=0.8`, `colsample_bytree=0.8`, `min_child_weight=5`, `reg_lambda=1.0`, `random_state=42`.
  - Explicaciones con SHAP (TreeExplainer).
- **Software:** Python 3.14, scikit-learn 1.9.1, xgboost 3.4.1, shap 0.54.1, lifelines 0.30.3 (ver `requirements.txt`).
- **Protocolo:** [`docs/protocolo.md`](docs/protocolo.md) (estructura TRIPOD+AI).
- **Licencia:** repositorio académico publico; los datos tienen sus propias licencias (ver README).
- **Contacto:** a través del repositorio en GitHub.

## Uso previsto

- **Uso principal:** investigación, docencia y para uso clínico intrahospitalario. Sirve para estudiar cuánto aporta el Hospital Frailty Risk Score (HFRS) a la predicción del desenlace compuesto a 90 días (muerte, reingreso o visita a urgencias) después del egreso de personas de 65 años o más, y para practicar el desarrollo y la validación de modelos en OMOP.
- **Usuarios previstos:** estudiantes, docentes, médicos e investigadores de ciencia de datos en salud.
- **Fuera de alcance:** cualquier uso clínico definitivo o administrativo. No sirve para decidir altas, seguimiento, asignación de recursos ni ningún tratamiento de personas reales ya que aun no se han validado todos los modelos anidados en datos clínicos reales de un tamaño de muestra adecuado. Los modelos se entrenaron con datos sintéticos y solo M0 se probó, de forma exploratoria, en 27 personas reales con un demo.

## Factores

- **Grupos relevantes:** edad, sexo, categoría de HFRS (<5, 5 a 15, >15), comorbilidades.
- **Factores del entorno:** codificación de diagnósticos (ICD-10 frente a ICD-9 traducido con GEM), tipo de hospital (sintético frente a terciario académico) y completitud del seguimiento.
- No se evaluó el desempeño por subgrupos de sexo, edad o raza/etnia.

## Métricas

- **Discriminación:** AUROC y AUPRC (referencia nula = prevalencia, 0.374).
- **Calibración:** pendiente de calibración (1 = ideal), calibración-en-lo-grande (CITL, observado − predicho; 0 = ideal), razón observado/esperado (O/E) y curvas de calibración.
- **Incertidumbre:** IC 95 % bootstrap percentil (1,000 réplicas, semilla 42); diferencias de AUROC pareadas.
- **Por qué:** el desenlace tiene una frecuencia importante  (37.4 %), así que AUROC y AUPRC son informativas. La calibración importa porque un modelo de riesgo se usaría por sus probabilidades, no solo por su orden.

## Datos de evaluación

- **Interna:** validación cruzada estratificada en 5 pliegues (semilla 42) en Synthea, con predicciones fuera de pliegue.
- **Externa exploratoria:** MIMIC-IV Clinical Database Demo v2.2 + MIMIC-IV-ED Demo v2.2 (PhysioNet, ODbL). Cohorte postegreso de 45 personas; 27 con seguimiento completo y 14 eventos (51.9 %). Solo se transportó M0.

## Datos de entrenamiento

- Synthea convertido a OMOP CDM (`omop_20k.duckdb`), 100 % sintético.
- Cohorte 1701: primer egreso a los 65 años o más, con 730 días de observación previa, lavado de 30 días, 2 o más visitas ambulatorias, creatinina, albúmina y TFGe en 365 días, multimorbilidad, sin cáncer y sin muerte el día del egreso o antes. De 11,745 egresos quedan 5,515 personas.
- Conjunto de entrenamiento de la logística y XGBoost: 5,372 personas con seguimiento completo, 2,009 eventos (37.4 %). Cox: 5,494 personas, 2,051 eventos.
- HFRS: 109 códigos ICD-10 de 3 caracteres, SNOMED → ICD10CM (`Mapped from`), ventana de 730 días, F00 asignado por G30. Mediana 0.6; solo 10 personas con HFRS > 15.

## Resultados cuantitativos

### Desarrollo (Synthea, validación cruzada, n = 5,372)

| Modelo | AUROC [IC 95 %] | AUPRC | Pendiente de calibración |
|---|---|---:|---:|
| M0 (HFRS) | 0.600 | — | 0.99 |
| M1 (+ edad, sexo) | 0.592 | — | 0.96 |
| M2 (+ comorbilidades, fármacos) | 0.689 | — | 0.97 |
| M3 (+ laboratorios, utilización, estancia) | 0.734 | 0.672 | 0.90 |
| XGBoost (variables de M3) | 0.810 [0.798-0.823] | 0.750 | 1.03 |

- XGBoost frente a M3: ΔAUROC +0.076 [0.065-0.087].
- Cox M3: C-index aparente 0.695; HFRS ajustado HR 1.03 [1.02-1.05] por punto.
- SHAP: `n_urgencias_365`, `estancia_indice_dias` y `n_ingredientes_30` son las variables más importantes; el HFRS es la 7.ª.

Los IC de todos los modelos están en [`docs/modelos.md`](docs/modelos.md) y [`docs/xgb_shap.md`](docs/xgb_shap.md).

### Validación externa exploratoria (MIMIC-IV Demo, M0)

M0 ajustado una vez en Synthea (intercepto −0.737; coeficiente del HFRS 0.116 por punto) y aplicado sin cambios.

| Métrica | Valor |
|---|---|
| Personas (seguimiento completo) / eventos | 27 / 14 |
| AUROC [IC 95 %] | 0.703 [0.488-0.894] |
| CITL (observado − predicho) | −0.091 |
| Pendiente de calibración | 0.83 |
| Razón O/E | 0.85 |

El IC del AUROC cruza 0.5. M0 sobreestima el riesgo cerca de un 15 % en promedio, porque el HFRS de MIMIC (mediana 7.6) está muy por encima del de Synthea (mediana 0.6).

## Consideraciones éticas

- **Datos:** el desarrollo usa solo datos sintéticos. MIMIC-IV Demo está desidentificada (HIPAA) y es de acceso abierto; sus microdatos no se versionan. No hay identificadores de persona en figuras ni documentos, ni credenciales en el repositorio (gitleaks antes de cada push y en CI).
- **Riesgo de mal uso:** un puntaje de fragilidad usado para decidir altas o recursos podría negar atención a personas mayores. Este modelo no está validado para eso.
- **Equidad:** no se evaluó el desempeño por sexo, edad o raza/etnia. El HFRS depende de cuánto y cómo se codifica, así que puede subestimar la fragilidad de quien tiene menos contacto con el sistema de salud.
- **Explicaciones:** SHAP describe el modelo, no causas. No debe usarse para recomendar intervenciones.
- **Uso de IA:** se declaró en [`docs/uso_ia.md`](docs/uso_ia.md).

## Advertencias y recomendaciones

- Los resultados de desarrollo reflejan los artefactos de Synthea (HFRS comprimido, muertes el día del egreso, hallazgos renales implausibles para valores de creatinina y TFG).
- El supuesto de riesgos proporcionales se viola en 17 de 37 variables del Cox de M3.
- Los faltantes de laboratorio son informativos; la imputación por mediana es una simplificación.
- La validación en MIMIC es exploratoria: n = 27, un solo hospital, reingresos y urgencias solo de ese hospital, extrapolación del HFRS fuera del rango de Synthea y error de medición del GEM ICD-9 → ICD-10 (8 códigos del HFRS sin origen ICD-9).
- Antes de cualquier uso fuera de la docencia haría falta validar en una base real grande (MIMIC-IV completo, All of Us o CPRD + HES) y recalibrar en el sitio de destino.
- Detalle completo en [`docs/limitaciones.md`](docs/limitaciones.md).
