-- HFRS por persona de la cohorte 1701.
-- Requiere una tabla temporal "cohorte" con subject_id y cohort_start_date.
WITH diagnosticos AS (
    -- (1) Traducción automática SNOMED -> ICD10CM, primeros 3 caracteres
    SELECT DISTINCT c.subject_id AS person_id, LEFT(i.concept_code, 3) AS codigo
    FROM cohorte c
    JOIN condition_occurrence co
      ON co.person_id = c.subject_id
     AND co.condition_start_date BETWEEN c.cohort_start_date - INTERVAL 730 DAY
                                     AND c.cohort_start_date
    JOIN concept_relationship cr
      ON cr.concept_id_1 = co.condition_concept_id
     AND cr.relationship_id = 'Mapped from'
     AND cr.invalid_reason IS NULL
    JOIN concept i
      ON i.concept_id = cr.concept_id_2
     AND i.vocabulary_id = 'ICD10CM'
    UNION
    -- (2) Tabla puente manual para diagnósticos sin traducción
    SELECT DISTINCT c.subject_id AS person_id, b.codigo_hfrs AS codigo
    FROM cohorte c
    JOIN condition_occurrence co
      ON co.person_id = c.subject_id
     AND co.condition_start_date BETWEEN c.cohort_start_date - INTERVAL 730 DAY
                                     AND c.cohort_start_date
    JOIN concept s
      ON s.concept_id = co.condition_concept_id
     AND s.vocabulary_id = 'SNOMED'
    JOIN read_csv_auto('referencias/puente_snomed_hfrs.csv') b
      ON b.concepto_snomed = s.concept_name
),
con_f00 AS (
    SELECT person_id, codigo, FALSE AS ajuste FROM diagnosticos
    UNION ALL
    -- F00 no existe en ICD10CM: se asigna a quien tiene G30 (convención G30+F00 de la OMS)
    SELECT DISTINCT person_id, 'F00' AS codigo, TRUE AS ajuste
    FROM diagnosticos WHERE codigo = 'G30'
),
puntos AS (
    SELECT f.person_id, f.codigo, f.ajuste, h.puntos
    FROM con_f00 f
    JOIN read_csv_auto('referencias/hfrs_codigos.csv') h ON h.codigo = f.codigo
)
SELECT c.subject_id AS person_id,
       c.cohort_start_date AS fecha_indice,
       COALESCE(SUM(p.puntos), 0) AS hfrs,
       COALESCE(SUM(p.puntos) FILTER (WHERE NOT p.ajuste), 0) AS hfrs_sin_f00,
       COALESCE(SUM(p.puntos) FILTER (WHERE p.codigo NOT IN ('Z60', 'Z73')), 0) AS hfrs_sin_social
FROM cohorte c
LEFT JOIN puntos p ON p.person_id = c.subject_id
GROUP BY c.subject_id, c.cohort_start_date
