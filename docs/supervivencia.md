# Supervivencia a 90 días según el HFRS

## Seguimiento

- Personas: 5,515
- Muertes a 90 días: 369 (6.7 %)
- Mediana del tiempo observado: 90.0 días [90.0-90.0]

El tiempo de las personas que murieron es el día de la muerte. El de las demás es el mínimo entre el seguimiento y 90 días (censura, incluida quien se pierde de vista antes de los 90 días).

## Terciles de la muestra

Se pidieron 3 terciles con `pd.qcut(..., duplicates='drop')`. Resultado: **3** grupo(s). Cortes: 0.0, 0.6, 2.4, 19.1.

- T1: 2,811 personas
- T2: 1,775 personas
- T3: 929 personas

## Log-rank

| Comparación | Estadístico | gl | p |
|---|---:|---:|---:|
| Categorías HFRS (global) | 64.62 | 2 | <0.001 |
| 5-15 vs <5 | 61.52 | 1 | <0.001 |
| 5-15 vs >15 | 0.09 | 1 | 0.758 |
| <5 vs >15 | 4.03 | 1 | 0.045 |
| Terciles (global) | 103.03 | 2 | <0.001 |

## Modelos de Cox

| Modelo | Variable | HR | IC 95 % | p | C-index |
|---|---|---:|---:|---:|---:|
| HFRS continuo, univariable | hfrs | 1.08 | 1.05-1.11 | <0.001 | 0.578 |
| HFRS continuo, ajustado por edad y sexo | hfrs | 1.07 | 1.04-1.10 | <0.001 | 0.617 |
| HFRS continuo, ajustado por edad y sexo | edad | 1.06 | 1.04-1.07 | <0.001 |  |
| HFRS continuo, ajustado por edad y sexo | hombre | 0.97 | 0.79-1.19 | 0.771 |  |
| Terciles (referencia T1) | C(tercil, Treatment('T1'))[T.T2] | 0.74 | 0.56-0.97 | 0.027 | 0.617 |
| Terciles (referencia T1) | C(tercil, Treatment('T1'))[T.T3] | 2.54 | 2.02-3.20 | <0.001 |  |

## Prueba de riesgos proporcionales (transformación rank)

| Modelo | Variable | Estadístico | p |
|---|---|---:|---:|
| HFRS continuo, univariable | hfrs | 18.96 | <0.001 |
| HFRS continuo, ajustado por edad y sexo | edad | 1.99 | 0.158 |
| HFRS continuo, ajustado por edad y sexo | hfrs | 18.10 | <0.001 |
| HFRS continuo, ajustado por edad y sexo | hombre | 0.14 | 0.705 |
| Terciles (referencia T1) | C(tercil, Treatment('T1'))[T.T2] | 5.34 | 0.021 |
| Terciles (referencia T1) | C(tercil, Treatment('T1'))[T.T3] | 43.35 | <0.001 |

## Limitaciones

El grupo de HFRS alto (>15) tiene 10 personas (2 muertes). La curva de Kaplan-Meier y el log-rank de ese grupo son inestables; por eso se informan también el HFRS continuo (HR por cada punto) y los terciles de la muestra. La mediana de supervivencia no se alcanza a los 90 días si la curva se queda por encima de 0.5.
