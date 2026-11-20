# Limitaciones

Estas limitaciones describen lo que permiten medir las bases usadas: Synthea convertida a OMOP (`omop_20k.duckdb`) para el desarrollo y MIMIC-IV Demo para la validación externa. 

## 1. Datos sintéticos (Synthea)

Los datos de desarrollo son 100 % sintéticos. 

- **Periodos de observación:** los 11,745 egresos iniciales ya tenían 730 días de observación previa.
- **Muertes el día del egreso o antes:** se excluyeron 370 personas. 
- **Hallazgos clínicamente implausibles en la Tabla 1:** la enfermedad renal crónica y la creatinina son menores en quienes mueren, y las medianas de la TFGe (11 frente a 21) no son plausibles desde el punto de vista biológico.
- **Función renal colineal:** `creatinina_ultima` y `tfge_ultima` entran juntas en M3. Sus HR ajustados no se interpretan por separado; lo que se observo es que la predicción no se afecta.
- **Variables no disponibles:** IL-1, cistatina C y METs no están en la base, así que no entraron a la matriz de 37 variables, como se habia planteado en el proyecto original.

## 2. Atrición y sesgo de selección

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

Selecciinar  dos visitas ambulatorias y analíticas previas como criterio de inclusión selecciona personas con más contacto con el sistema de salud. Los resultados no se pueden generalizar a quien llega al hospital sin seguimiento previo.

## 3. HFRS comprimido

| Categoría | Personas | % |
|---|---:|---:|
| Bajo (<5) | 5,208 | 94.4 % |
| Intermedio (5 a 15) | 297 | 5.4 % |
| Alto (>15) | 10 | 0.2 % |

- La mediana es 0.6 puntos y el máximo es 19.1. Se observó que Synthea casi no genera los diagnósticos de síndromes geriátricos que más pesan en el HFRS (caídas, delirium, úlceras por presión, incontinencia).
- El grupo alto tiene solo 10 personas: su curva de Kaplan-Meier y su comparación son muy inestables. Por eso se agregaron el HFRS continuo (por punto) y los terciles de la muestra.
- Con poca variabilidad, el AUROC de M0 (0.600) subestima lo que el HFRS podría discriminar en una población real.

## 4. Traducción del HFRS

- El HFRS se publicó en CIE-10 de la OMS. Aquí se usa SNOMED → ICD10CM (`Mapped from`) con 3 caracteres.
- **F00** no existe en ICD10CM: sus 7.1 puntos se asignan a G30. El puntaje sin ajuste está en `hfrs_sin_f00`.
- **Puente manual** de 9 conceptos SNOMED (`referencias/puente_snomed_hfrs.csv`). 


## 5. Desenlaces y seguimiento

- 143 personas (2.6 %) tienen seguimiento incompleto. Quedan fuera del análisis  (5,372 de 5,515) y se censuran en el Cox (5,494).
- Los reingresos y las urgencias solo se ven si quedan registrados en la base. 
- Para reingreso y urgencias, la muerte es un riesgo competitivo. El patrón inverso del reingreso por terciles (T1 20.7 % frente a T3 11.4 %) se explica en parte porque en T3 muere el 13.3 % antes de poder reingresar.

## 6. Modelos

- **Riesgos proporcionales:** en el Cox multivariable de M3 la prueba de Schoenfeld rechaza el supuesto en 17 de 37 variables. Los HR ajustados deben leerse como un promedio en el tiempo de 90 días; no son constantes.
- **C-index de Cox M3 (0.695) aparente:** se calcula en la misma muestra, no por validación cruzada.
- **Faltantes informativos:** la falta de un laboratorio depende del estado clínico (por ejemplo, falta la hemoglobina en 470 sobrevivientes y en 4 muertes). Los indicadores `_falta` capturan parte de esa información, pero la imputación por mediana supone algo que no se cumple. `albumina_falta`, `creatinina_falta` y `tfge_falta` se excluyeron justamente como datos faltantes.
- **XGBoost:** hiperparámetros fijos. Su ventaja frente a M3 (ΔAUROC +0.076) es interna a Synthea y no se ha validado en datos reales.
- **SHAP no es causal:** describe cómo usa el modelo cada variable. 

## 7. Validación externa en MIMIC-IV Demo (exploratoria)

- **Muestra mínima:** 45 personas en la cohorte postegreso; 27 con seguimiento completo y 14 eventos. El IC del AUROC (0.703 [0.488-0.894]) cruza 0.5: con dirección esperada, pero no se puede afirmar que M0 discrimine adecuadamente en MIMIC.
- **Calibración inestable:** la pendiente (0.83), la CITL (−0.091) y la razón O/E (0.85) se calcularon con muy pocos grupos; M0 sobreestima el riesgo en cerca de un 15 % . 
- **Un solo hospital:** Beth Israel Deaconess Medical Center (Boston), un centro terciario académico.
- **Seguimiento parcial:** solo se ven reingresos y urgencias en ese mismo hospital; los que ocurren en otros hospitales cuentan como «sin evento». La muerte fuera del hospital solo se registra hasta un año después del último egreso. 
- **Extrapolación:** el HFRS en MIMIC (mediana 7.6, máximo 25.3) está muy por encima del rango en el que se ajustó M0 en Synthea (mediana 0.6, máximo 19.1). 
- **Error de medición por el GEM:** 36 de las 45 personas tienen el ingreso índice codificado en ICD-9. La traducción con el GEM CMS 2018 es aproximada y de 1 a muchos (puede sobreasignar puntos). Además, 8 códigos del HFRS no tienen origen ICD-9 en el GEM (F00, J22, R02, R54, U80, X59, Y95, Z50), así que el HFRS puede quedar subestimado en esas personas; F00 se recupera en parte por G30.
- **Solo M0:** M3 y XGBoost no se transportaron porque varias variables son propias de Synthea y no hay potencia para 37 predictores.


## 8. Trabajo futuro

- **MIMIC-IV completo (v2.2 o posterior):** el mismo código funciona cambiando `--mimic` y `--ed`. Daría miles de personas de 65 años o más, y permitiría transportar M1 y mapear laboratorios para acercarse a M3.
- **All of Us (NIH):** está en OMOP, igual que la base de desarrollo, así que el SQL de cohorte y HFRS se podría reutilizar casi sin cambios. Sin embargo, el acceso depende de un convenio institucional.
- **CPRD + HES o UK Biobank:** la fuente original del HFRS (CIE-10 de la OMS, sin necesidad del ajuste F00).
- **Métodos:** Aquí se sugeriría seguir el siguiente pipelin de recalibración en el sitio externo, modelos con coeficientes que cambian con el tiempo para los riesgos proporcionales, Fine-Gray para reingreso y urgencias, y búsqueda de hiperparámetros con validación anidada.
