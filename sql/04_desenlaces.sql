-- Desenlaces a 90 días de la cohorte 1701 (días 1 a 90 tras el egreso).
-- Requiere la tabla temporal "cohorte". Valor vacío = no hubo el evento.
WITH muertes AS (
    SELECT c.subject_id AS person_id,
           MIN(DATE_DIFF('day', c.cohort_start_date, d.death_date)) AS dias
    FROM cohorte c
    JOIN death d ON d.person_id = c.subject_id
    WHERE d.death_date > c.cohort_start_date
      AND d.death_date <= c.cohort_start_date + INTERVAL 90 DAY
    GROUP BY c.subject_id
),
reingresos AS (
    SELECT c.subject_id AS person_id,
           MIN(DATE_DIFF('day', c.cohort_start_date, v.visit_start_date)) AS dias
    FROM cohorte c
    JOIN visit_occurrence v
      ON v.person_id = c.subject_id AND v.visit_concept_id = 9201
    WHERE v.visit_start_date > c.cohort_start_date
      AND v.visit_start_date <= c.cohort_start_date + INTERVAL 90 DAY
    GROUP BY c.subject_id
),
urgencias AS (
    SELECT c.subject_id AS person_id,
           MIN(DATE_DIFF('day', c.cohort_start_date, v.visit_start_date)) AS dias
    FROM cohorte c
    JOIN visit_occurrence v
      ON v.person_id = c.subject_id AND v.visit_concept_id = 9203
    WHERE v.visit_start_date > c.cohort_start_date
      AND v.visit_start_date <= c.cohort_start_date + INTERVAL 90 DAY
    GROUP BY c.subject_id
)
SELECT c.subject_id AS person_id,
       DATE_DIFF('day', c.cohort_start_date, c.cohort_end_date) AS dias_seguimiento,
       m.dias AS dias_muerte,
       r.dias AS dias_reingreso,
       u.dias AS dias_urgencias
FROM cohorte c
LEFT JOIN muertes m ON m.person_id = c.subject_id
LEFT JOIN reingresos r ON r.person_id = c.subject_id
LEFT JOIN urgencias u ON u.person_id = c.subject_id
