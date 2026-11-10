# Limitaciones

Estas limitaciones se observaron al calcular el HFRS, los desenlaces a 90 días, la Tabla 1 y el análisis de supervivencia sobre la base sintética Synthea convertida a OMOP (`omop_20k.duckdb`). 

## Datos sintéticos

Los datos son 100 % sintéticos. La validación externa en MIMIC-IV Demo (datos reales) esta pendiente para la entrega final.

## Atrición de la cohorte 

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
| − muerte el día del egreso o antes | 5,515 | 370 |

Los 11,745 egresos iniciales ya tenían 730 días de observación previa: al parecer es un artefacto de cómo Synthea construye los periodos. El criterio que más reduce la muestra es exigir dos visitas ambulatorias, seguido de creatinina y albúmina. Exigir esas analíticas como criterio de inclusión puede introducir sesgo; se mantiene para se comentara para la evaluación final.

Se excluyeron 370 personas con muerte el día del egreso o antes. En una cohorte de egresos esa muerte no debería existir: es un posible artefacto de Synthea.

## Traducción del HFRS a esta base

El HFRS se publicó con códigos CIE-10 de la OMS. Esta base no tiene ese vocabulario; los diagnósticos se traducen de SNOMED a ICD10CM con la relación `Mapped from` y se usan los primeros tres caracteres del código.

- **F00 no existe en ICD10CM.** En la CIE-10 de la OMS, la demencia en la enfermedad de Alzheimer (F00, 7.1 puntos) suele acompañar a G30. Aquí se asignan esos 7.1 puntos a quien tiene G30. El puntaje sin ese ajuste queda en `hfrs_sin_f00`.
- **Puente manual de 9 conceptos.** Algunos conceptos SNOMED frecuentes en Synthea no tienen traducción automática a un código del HFRS. Se mapean a mano en `referencias/puente_snomed_hfrs.csv`.
- **Z60 y Z73.** En esta base salen de «Social isolation» y «Stress». Como son muy frecuentes y pueden inflar el puntaje, se guarda `hfrs_sin_social` como análisis de sensibilidad.

## Distribución comprimida del HFRS

| Categoría | Personas | % |
|---|---:|---:|
| Bajo (<5) | 5,208 | 94.4 % |
| Intermedio (5 a 15) | 297 | 5.4 % |
| Alto (>15) | 10 | 0.2 % |

La mediana es 0.6 puntos (el solo código de «Stress») y el máximo 19.1. Synthea casi no genera los diagnósticos de condiciones relacionadas a personas mayores que más pesan en el HFRS (caídas, delirium, úlceras por presión, incontinencia).

Consecuencias:

- El grupo alto tiene 10 personas y 2 muertes. Su curva de Kaplan-Meier y sus comparaciones log-rank son inestables (5-15 vs >15: p = 0.758 por falta de poder, no por ausencia de diferencia). Se mantienen las categorías de la propuesta y se agregan el HFRS continuo y los terciles de la muestra.
- Por los empates en 0.6, el primer tercil quedó con 2,811 personas, el segundo con 1,775 y el tercero con 929 (cortes 0.0, 0.6, 2.4 y 19.1). Los terciles no son del mismo tamaño.
- Esta limitación motiva la validación en MIMIC-IV Demo.

## Hallazgos poco plausibles en la Tabla 1

La Tabla 1 compara a las 5,372 personas con seguimiento completo (5,003 sobreviven, 369 mueren). Algunas diferencias van en sentido contrario a lo clínicamente esperado y se atribuyen a cómo Synthea genera los datos:

- **Enfermedad renal crónica y creatinina más bajas en quienes mueren** (ERC 29.5 % vs 41.2 %; creatinina mediana 1.4 vs 2.7).
- **TFGe con medianas implausibles** (11.2 en sobrevivientes y 21.3 en fallecidos).  No se verificaron unidades en `unit_concept_id`; queda pendiente.
- **Sesgo de registro en hemoglobina.** Falta en 470 sobrevivientes y solo en 4 fallecidos (tener hemoglobina: 90.6 % vs 98.9 %). Quien está más enfermo tiene más análisis. 
- Creatinina, albúmina y TFGe están disponibles en el 100 % porque son criterios de inclusión.

Por eso estas variables se interpretarán con cautela en los modelos multivariables.

## Supervivencia preliminar

- **Riesgos proporcionales.** La prueba de Schoenfeld (transformación rank) rechaza la proporcionalidad para el HFRS continuo (p < 0.001) y para los terciles. El efecto del HFRS cambia en los 90 días. Los HR son un promedio en el tiempo; en la entrega final se probará estratificar o agregar interacción con el tiempo.
- **Relación no lineal.** El tercil 2 tuvo HR 0.74 (IC 95 % 0.56-0.97) frente al tercil 1, y el tercil 3 HR 2.54 (2.02-3.20). 
- **Discriminación modesta.** C-index 0.578 con el HFRS solo y 0.617 con edad y sexo. Es la referencia (M0) que los modelos M1 a M3 deberán superar.
- La mediana de supervivencia no se alcanza a los 90 días (la curva queda arriba de 0.5).

## Variables que quizá no estén

IL-1, cistatina C y METs probablemente no estén en esta base. Falta verificarlo. Si no aparecen, no entrarán al modelo multivariable y se declarará en la entrega final.

## Desenlaces a 90 días

En las 5,515 personas:

- 369 muertes (6.7 %)
- 910 reingresos, visita 9201 (16.5 %)
- 1,082 visitas a urgencias, visita 9203 (19.6 %)
- 2,051 con el desenlace compuesto (37.2 %)
- 143 con seguimiento incompleto (2.6 %): se censuran en supervivencia y se excluyen de la Tabla 1

## Qué no cubre este avance

Este documento describe el avance intermedio . Faltan para la entrega final los modelos anidados M1 a M3, XGBoost con SHAP, curvas ROC y de calibración, AUPRC, la incidencia acumulada con la prueba de Gray para reingreso y urgencias, y la validación en MIMIC-IV Demo.
