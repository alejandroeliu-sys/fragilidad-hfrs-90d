-- Matriz de features pre-índice de la cohorte 
-- Requiere de la tabla temporal "cohorte". Día 0 = egreso (fecha índice).
-- Ventanas: comorbilidades (-inf, -1] | fármacos, laboratorios y visitas [-365, -1]
--           estancia índice: la hospitalización que termina el día 0.
-- No usa información posterior al egreso.
WITH coh AS (
    SELECT subject_id AS person_id, cohort_start_date AS fecha_indice
    FROM cohorte
),
-- PERSON y OBSERVATION_PERIOD: 
nacimiento AS (
    SELECT p.person_id, p.gender_concept_id,
           MAKE_DATE(p.year_of_birth, COALESCE(p.month_of_birth, 1),
                     COALESCE(p.day_of_birth, 1)) AS fecha_nacimiento
    FROM person p
),
-- Inicio del periodo de observación que contiene la fecha índice
obs AS (
    SELECT c.person_id, MIN(op.observation_period_start_date) AS obs_inicio
    FROM coh c
    JOIN observation_period op
      ON op.person_id = c.person_id
     AND c.fecha_indice BETWEEN op.observation_period_start_date
                            AND op.observation_period_end_date
    GROUP BY c.person_id
),
persona AS (
    SELECT c.person_id,
           CASE
               WHEN MONTH(c.fecha_indice) > MONTH(n.fecha_nacimiento)
                 OR (MONTH(c.fecha_indice) = MONTH(n.fecha_nacimiento)
                     AND DAY(c.fecha_indice) >= DAY(n.fecha_nacimiento))
               THEN YEAR(c.fecha_indice) - YEAR(n.fecha_nacimiento)
               ELSE YEAR(c.fecha_indice) - YEAR(n.fecha_nacimiento) - 1
           END AS edad,
           CASE WHEN n.gender_concept_id = 8507 THEN 1 ELSE 0 END AS sexo_masc,
           DATE_DIFF('day', o.obs_inicio, c.fecha_indice) AS obs_previa_dias
    FROM coh c
    JOIN nacimiento n ON n.person_id = c.person_id
    LEFT JOIN obs o ON o.person_id = c.person_id
),
-- Ancestro y descendientes de las 7 comorbilidades. 
conceptos_dx AS (
    SELECT ancestor_concept_id AS ancestro, descendant_concept_id AS concept_id
    FROM concept_ancestor
    WHERE ancestor_concept_id IN (201826, 316139, 46271022, 4182210, 4185932, 320128, 439777)
    UNION
    SELECT x, x FROM (VALUES (201826), (316139), (46271022), (4182210),
                             (4185932), (320128), (439777)) t(x)
),
-- CONDITION_OCCURRENCE: diagnósticos en (-inf, -1]
dx AS (
    SELECT c.person_id,
           MAX(CASE WHEN k.ancestro = 201826   THEN 1 ELSE 0 END) AS dm2_dx,
           MAX(CASE WHEN k.ancestro = 316139   THEN 1 ELSE 0 END) AS ic_dx,
           MAX(CASE WHEN k.ancestro = 46271022 THEN 1 ELSE 0 END) AS erc_dx,
           MAX(CASE WHEN k.ancestro = 4182210  THEN 1 ELSE 0 END) AS demencia_dx,
           MAX(CASE WHEN k.ancestro = 4185932  THEN 1 ELSE 0 END) AS cardiop_isq_dx,
           MAX(CASE WHEN k.ancestro = 320128   THEN 1 ELSE 0 END) AS hta_dx,
           MAX(CASE WHEN k.ancestro = 439777   THEN 1 ELSE 0 END) AS anemia_dx
    FROM coh c
    JOIN condition_occurrence o
      ON o.person_id = c.person_id
     AND o.condition_start_date <= c.fecha_indice - INTERVAL 1 DAY
    JOIN conceptos_dx k ON k.concept_id = o.condition_concept_id
    GROUP BY c.person_id
),
-- DRUG_EXPOSURE: cada registro en [-365, -1] 
rx AS (
    SELECT c.person_id,
           x.drug_exposure_start_date AS fecha,
           DATE_DIFF('day', c.fecha_indice, x.drug_exposure_start_date) AS dia,
           ca.ancestor_concept_id AS ingrediente
    FROM coh c
    JOIN drug_exposure x
      ON x.person_id = c.person_id
     AND x.drug_exposure_start_date BETWEEN c.fecha_indice - INTERVAL 365 DAY
                                        AND c.fecha_indice - INTERVAL 1 DAY
    JOIN concept_ancestor ca ON ca.descendant_concept_id = x.drug_concept_id
    JOIN concept i
      ON i.concept_id = ca.ancestor_concept_id
     AND i.concept_class_id = 'Ingredient'
),
farmacos AS (
    SELECT person_id,
           COUNT(DISTINCT ingrediente)                           AS n_ingredientes_365,
           COUNT(DISTINCT ingrediente) FILTER (WHERE dia >= -30) AS n_ingredientes_30,
           -- Comorbilidades: >= 2 registros en fechas distintas
           CASE WHEN COUNT(DISTINCT fecha) FILTER (
                     WHERE ingrediente IN (1503297, 1596977, 46221581)) >= 2
                THEN 1 ELSE 0 END AS dm_inferida,    
           CASE WHEN COUNT(DISTINCT fecha) FILTER (
                     WHERE ingrediente IN (1308216, 974166, 1332418, 1367500)) >= 2
                THEN 1 ELSE 0 END AS hta_inferida,   
           CASE WHEN COUNT(DISTINCT fecha) FILTER (WHERE ingrediente = 956874) >= 2
                 AND COUNT(*) FILTER (WHERE ingrediente IN (1346823, 1307046)) >= 1
                THEN 1 ELSE 0 END AS ic_inferida     
    FROM rx
    GROUP BY person_id
),
-- MEASUREMENT: valores en [-365, -1]. 
-- creatinina junta los dos conceptos que usa sql/05 (3016723 y 3051825).
lab_crudo AS (
    SELECT c.person_id,
           CASE m.measurement_concept_id
               WHEN 3024561  THEN 'albumina'
               WHEN 3016723  THEN 'creatinina'
               WHEN 3051825  THEN 'creatinina'
               WHEN 3004295  THEN 'urea'
               WHEN 3000963  THEN 'hemoglobina'
               WHEN 46236952 THEN 'tfge'
               WHEN 3004249  THEN 'pas'
               WHEN 3038553  THEN 'imc'
           END AS prueba,
           m.measurement_id,
           m.measurement_date,
           m.value_as_number AS valor,
           DATE_DIFF('day', c.fecha_indice, m.measurement_date) AS dia
    FROM coh c
    JOIN measurement m
      ON m.person_id = c.person_id
     AND m.measurement_date BETWEEN c.fecha_indice - INTERVAL 365 DAY
                                AND c.fecha_indice - INTERVAL 1 DAY
     AND m.measurement_concept_id IN (3024561, 3016723, 3051825, 3004295,
                                      3000963, 46236952, 3004249, 3038553)
     AND m.value_as_number IS NOT NULL
),
-- rn = 1, medición más reciente de cada prueba.
lab AS (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY person_id, prueba
               ORDER BY measurement_date DESC, measurement_id DESC
           ) AS rn
    FROM lab_crudo
),
labs AS (
    SELECT person_id,
           -- Albúmina (g/dL): 
           MAX(valor) FILTER (WHERE prueba = 'albumina' AND rn = 1) AS albumina_ultima,
           COUNT(*)   FILTER (WHERE prueba = 'albumina')            AS albumina_n,
           CASE WHEN COUNT(DISTINCT dia) FILTER (WHERE prueba = 'albumina') >= 3
                THEN REGR_SLOPE(valor, dia / 365.0) FILTER (WHERE prueba = 'albumina')
           END AS albumina_pendiente,
           CASE WHEN COUNT(DISTINCT dia) FILTER (WHERE prueba = 'albumina') >= 3
                THEN STDDEV_SAMP(valor) FILTER (WHERE prueba = 'albumina')
           END AS albumina_de,
           -- Creatinina (mg/dL)
           MAX(valor) FILTER (WHERE prueba = 'creatinina' AND rn = 1) AS creatinina_ultima,
           COUNT(*)   FILTER (WHERE prueba = 'creatinina')            AS creatinina_n,
           CASE WHEN COUNT(DISTINCT dia) FILTER (WHERE prueba = 'creatinina') >= 3
                THEN REGR_SLOPE(valor, dia / 365.0) FILTER (WHERE prueba = 'creatinina')
           END AS creatinina_pendiente,
           -- Urea / BUN (mg/dL)
           MAX(valor) FILTER (WHERE prueba = 'urea' AND rn = 1) AS urea_ultima,
           COUNT(*)   FILTER (WHERE prueba = 'urea')            AS urea_n,
           CASE WHEN COUNT(DISTINCT dia) FILTER (WHERE prueba = 'urea') >= 3
                THEN REGR_SLOPE(valor, dia / 365.0) FILTER (WHERE prueba = 'urea')
           END AS urea_pendiente,
           -- Últimos valores: hemoglobina (g/dL), TFGe (mL/min/1.73 m2),
           -- presión sistólica (mmHg) e IMC (kg/m2)
           MAX(valor) FILTER (WHERE prueba = 'hemoglobina' AND rn = 1) AS hemoglobina_ultima,
           MAX(valor) FILTER (WHERE prueba = 'tfge' AND rn = 1)        AS tfge_ultima,
           MAX(valor) FILTER (WHERE prueba = 'pas' AND rn = 1)         AS pas_ultima,
           MAX(valor) FILTER (WHERE prueba = 'imc' AND rn = 1)         AS imc_ultimo
    FROM lab
    GROUP BY person_id
),
-- VISIT_OCCURRENCE: visitas que empiezan en [-365, -1]. Las hospitalizaciones
-- previas deben terminar antes del índice, para no contar la estancia índice.
visitas AS (
    SELECT c.person_id,
           COUNT(*) FILTER (WHERE v.visit_concept_id = 9202) AS n_ambulatorias_365,
           COUNT(*) FILTER (WHERE v.visit_concept_id = 9201
                              AND v.visit_end_date <= c.fecha_indice - INTERVAL 1 DAY)
                                                             AS n_hosp_365,
           COUNT(*) FILTER (WHERE v.visit_concept_id = 9203) AS n_urgencias_365
    FROM coh c
    JOIN visit_occurrence v
      ON v.person_id = c.person_id
     AND v.visit_start_date BETWEEN c.fecha_indice - INTERVAL 365 DAY
                                AND c.fecha_indice - INTERVAL 1 DAY
    GROUP BY c.person_id
),
-- Duración de la hospitalización índice (se conoce al momento del egreso)
estancia AS (
    SELECT c.person_id,
           MAX(DATE_DIFF('day', v.visit_start_date, v.visit_end_date)) AS estancia_indice_dias
    FROM coh c
    JOIN visit_occurrence v
      ON v.person_id = c.person_id
     AND v.visit_concept_id = 9201
     AND v.visit_end_date = c.fecha_indice
    GROUP BY c.person_id
)
SELECT c.person_id,
       c.fecha_indice,
       pe.edad, pe.sexo_masc, pe.obs_previa_dias,
       COALESCE(dx.dm2_dx, 0)         AS dm2_dx,
       COALESCE(dx.ic_dx, 0)          AS ic_dx,
       COALESCE(dx.erc_dx, 0)         AS erc_dx,
       COALESCE(dx.demencia_dx, 0)    AS demencia_dx,
       COALESCE(dx.cardiop_isq_dx, 0) AS cardiop_isq_dx,
       COALESCE(dx.hta_dx, 0)         AS hta_dx,
       COALESCE(dx.anemia_dx, 0)      AS anemia_dx,
       COALESCE(f.n_ingredientes_365, 0) AS n_ingredientes_365,
       COALESCE(f.n_ingredientes_30, 0)  AS n_ingredientes_30,
       COALESCE(f.dm_inferida, 0)        AS dm_inferida,
       COALESCE(f.hta_inferida, 0)       AS hta_inferida,
       COALESCE(f.ic_inferida, 0)        AS ic_inferida,
       l.albumina_ultima, COALESCE(l.albumina_n, 0) AS albumina_n,
       l.albumina_pendiente, l.albumina_de,
       l.creatinina_ultima, COALESCE(l.creatinina_n, 0) AS creatinina_n,
       l.creatinina_pendiente,
       l.urea_ultima, COALESCE(l.urea_n, 0) AS urea_n, l.urea_pendiente,
       l.hemoglobina_ultima, l.tfge_ultima, l.pas_ultima, l.imc_ultimo,
       COALESCE(v.n_ambulatorias_365, 0) AS n_ambulatorias_365,
       COALESCE(v.n_hosp_365, 0)         AS n_hosp_365,
       COALESCE(v.n_urgencias_365, 0)    AS n_urgencias_365,
       e.estancia_indice_dias
FROM coh c
JOIN persona pe      ON pe.person_id = c.person_id
LEFT JOIN dx         ON dx.person_id = c.person_id
LEFT JOIN farmacos f ON f.person_id  = c.person_id
LEFT JOIN labs l     ON l.person_id  = c.person_id
LEFT JOIN visitas v  ON v.person_id  = c.person_id
LEFT JOIN estancia e ON e.person_id  = c.person_id
ORDER BY c.person_id
