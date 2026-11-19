# Análisis univariado del desenlace compuesto a 90 días

Personas unidas: 5,515. El Cox usa el tiempo hasta el compuesto o la censura en `min(dias_seguimiento, 90)`; se excluye a quien no tiene tiempo de observación (tiempo ≤ 0): quedan 5,494 personas y 2,051 eventos. La logística se ajusta solo en quienes tienen `seguimiento_completo` (5,372 personas, 2,009 eventos). Cada modelo es univariado y usa casos completos de esa variable (la n puede cambiar). Las continuas se reportan por unidad natural; el HFRS, por punto. El Cox es el de `lifelines.CoxPHFitter` (sin penalización). La logística es el MLE sin penalización (IRLS) de un intercepto y un predictor.

Un guion (—) significa que no se pudo estimar: la variable era constante, estaba vacía, no hubo eventos o no eventos, o el ajuste no convergió.

## Demografía

| Variable | n Cox | Eventos | HR [IC 95%] | p | n log. | Eventos | OR [IC 95%] | p |
|---|---:|---:|---|---:|---:|---:|---|---:|
| `edad` | 5,494 | 2,051 | 1.014 [1.007-1.020] | <0.001 | 5,372 | 2,009 | 1.021 [1.013-1.030] | <0.001 |
| `sexo_masc` | 5,494 | 2,051 | 0.98 [0.90-1.07] | 0.710 | 5,372 | 2,009 | 1.00 [0.89-1.12] | 0.990 |
| `obs_previa_dias` | 5,494 | 2,051 | 1.0000 [1.0000-1.0000] | <0.001 | 5,372 | 2,009 | 1.0000 [1.0000-1.0001] | <0.001 |

## Comorbilidades

| Variable | n Cox | Eventos | HR [IC 95%] | p | n log. | Eventos | OR [IC 95%] | p |
|---|---:|---:|---|---:|---:|---:|---|---:|
| `dm2_dx` | 5,494 | 2,051 | 1.42 [1.29-1.57] | <0.001 | 5,372 | 2,009 | 1.62 [1.42-1.85] | <0.001 |
| `ic_dx` | 5,494 | 2,051 | 1.09 [0.98-1.22] | 0.103 | 5,372 | 2,009 | 1.26 [1.10-1.45] | 0.001 |
| `erc_dx` | 5,494 | 2,051 | 1.58 [1.44-1.72] | <0.001 | 5,372 | 2,009 | 1.95 [1.74-2.19] | <0.001 |
| `demencia_dx` | 5,494 | 2,051 | 1.99 [1.77-2.23] | <0.001 | 5,372 | 2,009 | 2.66 [2.23-3.16] | <0.001 |
| `cardiop_isq_dx` | 5,494 | 2,051 | 1.12 [0.99-1.26] | 0.062 | 5,372 | 2,009 | 1.07 [0.93-1.24] | 0.352 |
| `hta_dx` | 5,494 | 2,051 | 1.13 [1.03-1.23] | 0.008 | 5,372 | 2,009 | 1.22 [1.09-1.37] | <0.001 |
| `anemia_dx` | 5,494 | 2,051 | 1.04 [0.96-1.14] | 0.338 | 5,372 | 2,009 | 1.08 [0.96-1.21] | 0.193 |

## Fármacos

| Variable | n Cox | Eventos | HR [IC 95%] | p | n log. | Eventos | OR [IC 95%] | p |
|---|---:|---:|---|---:|---:|---:|---|---:|
| `n_ingredientes_365` | 5,494 | 2,051 | 1.036 [1.027-1.046] | <0.001 | 5,372 | 2,009 | 1.031 [1.020-1.043] | <0.001 |
| `n_ingredientes_30` | 5,494 | 2,051 | 1.07 [1.06-1.07] | <0.001 | 5,372 | 2,009 | 1.06 [1.05-1.07] | <0.001 |
| `dm_inferida` | 5,494 | 2,051 | 1.79 [1.64-1.96] | <0.001 | 5,372 | 2,009 | 2.29 [2.03-2.59] | <0.001 |
| `hta_inferida` | 5,494 | 2,051 | 1.35 [1.23-1.47] | <0.001 | 5,372 | 2,009 | 1.58 [1.41-1.77] | <0.001 |
| `ic_inferida` | 5,494 | 2,051 | 1.03 [0.90-1.19] | 0.629 | 5,372 | 2,009 | 1.16 [0.97-1.39] | 0.113 |

## Laboratorios y signos

| Variable | n Cox | Eventos | HR [IC 95%] | p | n log. | Eventos | OR [IC 95%] | p |
|---|---:|---:|---|---:|---:|---:|---|---:|
| `albumina_ultima` | 5,472 | 2,031 | 0.95 [0.87-1.04] | 0.255 | 5,352 | 1,991 | 0.92 [0.82-1.03] | 0.154 |
| `albumina_n` | 5,494 | 2,051 | 0.988 [0.979-0.997] | 0.007 | 5,372 | 2,009 | 0.992 [0.981-1.003] | 0.163 |
| `albumina_pendiente` | 3,118 | 1,143 | 0.9994 [0.9956-1.0032] | 0.749 | 3,053 | 1,131 | 1.000 [0.995-1.004] | 0.846 |
| `albumina_de` | 3,118 | 1,143 | 3.44 [2.41-4.92] | <0.001 | 3,053 | 1,131 | 4.06 [2.57-6.41] | <0.001 |
| `creatinina_ultima` | 5,488 | 2,045 | 0.994 [0.983-1.005] | 0.270 | 5,367 | 2,004 | 0.994 [0.981-1.007] | 0.380 |
| `creatinina_n` | 5,494 | 2,051 | 1.027 [1.024-1.030] | <0.001 | 5,372 | 2,009 | 1.041 [1.036-1.046] | <0.001 |
| `creatinina_pendiente` | 4,116 | 1,564 | 0.982 [0.976-0.989] | <0.001 | 4,025 | 1,540 | 0.975 [0.967-0.983] | <0.001 |
| `urea_ultima` | 4,915 | 1,852 | 0.996 [0.984-1.008] | 0.481 | 4,810 | 1,819 | 0.995 [0.980-1.010] | 0.515 |
| `urea_n` | 5,494 | 2,051 | 1.024 [1.019-1.028] | <0.001 | 5,372 | 2,009 | 1.035 [1.029-1.042] | <0.001 |
| `urea_pendiente` | 2,393 | 1,049 | 1.0001 [0.9965-1.0037] | 0.954 | 2,342 | 1,033 | 1.000 [0.995-1.005] | 0.918 |
| `hemoglobina_ultima` | 4,890 | 1,817 | 1.05 [1.02-1.07] | <0.001 | 4,778 | 1,781 | 1.06 [1.03-1.10] | <0.001 |
| `tfge_ultima` | 5,478 | 2,036 | 0.9981 [0.9969-0.9992] | <0.001 | 5,358 | 1,996 | 0.9988 [0.9974-1.0002] | 0.083 |
| `pas_ultima` | 5,421 | 2,035 | 0.9978 [0.9953-1.0002] | 0.076 | 5,300 | 1,993 | 0.995 [0.992-0.998] | 0.003 |
| `imc_ultimo` | 5,415 | 2,033 | 1.005 [0.984-1.026] | 0.652 | 5,294 | 1,991 | 1.008 [0.981-1.036] | 0.558 |

## Utilización y estancia

| Variable | n Cox | Eventos | HR [IC 95%] | p | n log. | Eventos | OR [IC 95%] | p |
|---|---:|---:|---|---:|---:|---:|---|---:|
| `n_ambulatorias_365` | 5,494 | 2,051 | 0.9988 [0.9977-0.9999] | 0.038 | 5,372 | 2,009 | 0.9993 [0.9978-1.0008] | 0.354 |
| `n_hosp_365` | 5,494 | 2,051 | 1.14 [1.09-1.19] | <0.001 | 5,372 | 2,009 | 1.70 [1.25-2.31] | <0.001 |
| `n_urgencias_365` | 5,494 | 2,051 | 1.07 [1.06-1.07] | <0.001 | 5,372 | 2,009 | 1.18 [1.16-1.21] | <0.001 |
| `estancia_indice_dias` | 5,494 | 2,051 | 0.979 [0.969-0.990] | <0.001 | 5,372 | 2,009 | 0.980 [0.968-0.993] | 0.002 |

## HFRS

| Variable | n Cox | Eventos | HR [IC 95%] | p | n log. | Eventos | OR [IC 95%] | p |
|---|---:|---:|---|---:|---:|---:|---|---:|
| `hfrs` | 5,494 | 2,051 | 1.08 [1.07-1.10] | <0.001 | 5,372 | 2,009 | 1.12 [1.10-1.15] | <0.001 |

## Indicadores de faltante

| Variable | n Cox | Eventos | HR [IC 95%] | p | n log. | Eventos | OR [IC 95%] | p |
|---|---:|---:|---|---:|---:|---:|---|---:|
| `albumina_falta` | 5,494 | 2,051 | 8.88 [5.71-13.81] | <0.001 | 5,372 | 2,009 | 15.19 [3.52-65.55] | <0.001 |
| `creatinina_falta` | 5,494 | 2,051 | — | — | 5,372 | 2,009 | — | — |
| `urea_falta` | 5,494 | 2,051 | 0.97 [0.84-1.13] | 0.708 | 5,372 | 2,009 | 0.84 [0.70-1.01] | 0.063 |
| `hemoglobina_falta` | 5,494 | 2,051 | 0.97 [0.84-1.11] | 0.613 | 5,372 | 2,009 | 1.05 [0.88-1.25] | 0.598 |
| `tfge_falta` | 5,494 | 2,051 | 10.13 [6.09-16.87] | <0.001 | 5,372 | 2,009 | 21.90 [2.86-167.51] | 0.003 |
| `pas_falta` | 5,494 | 2,051 | 0.52 [0.32-0.85] | 0.009 | 5,372 | 2,009 | 0.47 [0.27-0.83] | 0.009 |
| `imc_falta` | 5,494 | 2,051 | 0.55 [0.34-0.87] | 0.011 | 5,372 | 2,009 | 0.50 [0.29-0.85] | 0.010 |

## Limitaciones

- Los modelos son univariados: no hay ajuste por confusores.
- En el Cox se dejaron fuera 21 personas con tiempo ≤ 0.
- La logística no incluye a 143 personas con seguimiento incompleto, de las cuales 42 ya habían tenido el compuesto (reingreso o urgencias) antes de perderse de vista.
- Los faltantes no se imputan; cada fila reporta la n de ese modelo.
- Un efecto por unidad muy cercano a 1 (por ejemplo, `obs_previa_dias` por un día) puede ser significativo y aun así verse casi como 1.00.
