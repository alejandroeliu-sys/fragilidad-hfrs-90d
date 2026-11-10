-- Características basales de la cohorte 1701 (edad, sexo, comorbilidades y laboratorios).
-- Requiere la tabla temporal "cohorte".
WITH nacimiento AS (
    -- Fecha de nacimiento con año, mes y día. Si faltan mes o día, se usa 1.
    -- Se elige este cálculo, y no birth_datetime, porque esa columna a veces viene vacía.
    SELECT p.person_id,
           p.gender_concept_id,
           MAKE_DATE(
               p.year_of_birth,
               COALESCE(p.month_of_birth, 1),
               COALESCE(p.day_of_birth, 1)
           ) AS fecha_nacimiento
    FROM person p
),
edad_sexo AS (
    -- Años cumplidos en la fecha índice (no se usa DATE_DIFF('year'), que en DuckDB
    -- puede contar un año de más si el cumpleaños aún no ha llegado).
    SELECT c.subject_id AS person_id,
           CASE
               WHEN MONTH(c.cohort_start_date) > MONTH(n.fecha_nacimiento)
                 OR (MONTH(c.cohort_start_date) = MONTH(n.fecha_nacimiento)
                     AND DAY(c.cohort_start_date) >= DAY(n.fecha_nacimiento))
               THEN YEAR(c.cohort_start_date) - YEAR(n.fecha_nacimiento)
               ELSE YEAR(c.cohort_start_date) - YEAR(n.fecha_nacimiento) - 1
           END AS edad,
           CASE WHEN n.gender_concept_id = 8507 THEN 1 ELSE 0 END AS hombre
    FROM cohorte c
    JOIN nacimiento n ON n.person_id = c.subject_id
),
-- El ancestro y todos sus descendientes. El UNION agrega el propio código
-- por si concept_ancestor no trae la fila de distancia 0.
conceptos_dm2 AS (
    SELECT descendant_concept_id AS concept_id
    FROM concept_ancestor
    WHERE ancestor_concept_id = 201826
    UNION
    SELECT 201826
),
conceptos_ic AS (
    SELECT descendant_concept_id AS concept_id
    FROM concept_ancestor
    WHERE ancestor_concept_id = 316139
    UNION
    SELECT 316139
),
conceptos_erc AS (
    SELECT descendant_concept_id AS concept_id
    FROM concept_ancestor
    WHERE ancestor_concept_id = 46271022
    UNION
    SELECT 46271022
),
conceptos_demencia AS (
    SELECT descendant_concept_id AS concept_id
    FROM concept_ancestor
    WHERE ancestor_concept_id = 4182210
    UNION
    SELECT 4182210
),
-- Comorbilidades en la ventana (-∞, -1]: cualquier fecha estrictamente anterior al egreso.
dm2 AS (
    SELECT DISTINCT c.subject_id AS person_id
    FROM cohorte c
    JOIN condition_occurrence co
      ON co.person_id = c.subject_id
     AND co.condition_start_date < c.cohort_start_date
    JOIN conceptos_dm2 d ON d.concept_id = co.condition_concept_id
),
ic AS (
    SELECT DISTINCT c.subject_id AS person_id
    FROM cohorte c
    JOIN condition_occurrence co
      ON co.person_id = c.subject_id
     AND co.condition_start_date < c.cohort_start_date
    JOIN conceptos_ic d ON d.concept_id = co.condition_concept_id
),
erc AS (
    SELECT DISTINCT c.subject_id AS person_id
    FROM cohorte c
    JOIN condition_occurrence co
      ON co.person_id = c.subject_id
     AND co.condition_start_date < c.cohort_start_date
    JOIN conceptos_erc d ON d.concept_id = co.condition_concept_id
),
demencia AS (
    SELECT DISTINCT c.subject_id AS person_id
    FROM cohorte c
    JOIN condition_occurrence co
      ON co.person_id = c.subject_id
     AND co.condition_start_date < c.cohort_start_date
    JOIN conceptos_demencia d ON d.concept_id = co.condition_concept_id
),
-- Último valor en [-365, 0] (incluye el día del egreso). Se toma el más reciente;
-- si hay empate en la fecha, el measurement_id más alto.
creatinina AS (
    SELECT c.subject_id AS person_id,
           m.value_as_number AS creatinina
    FROM cohorte c
    JOIN measurement m
      ON m.person_id = c.subject_id
     AND m.measurement_concept_id IN (3016723, 3051825)
     AND m.value_as_number IS NOT NULL
     AND m.measurement_date BETWEEN c.cohort_start_date - INTERVAL 365 DAY
                                 AND c.cohort_start_date
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY c.subject_id
        ORDER BY m.measurement_date DESC, m.measurement_id DESC
    ) = 1
),
albumina AS (
    SELECT c.subject_id AS person_id,
           m.value_as_number AS albumina
    FROM cohorte c
    JOIN measurement m
      ON m.person_id = c.subject_id
     AND m.measurement_concept_id = 3024561
     AND m.value_as_number IS NOT NULL
     AND m.measurement_date BETWEEN c.cohort_start_date - INTERVAL 365 DAY
                                 AND c.cohort_start_date
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY c.subject_id
        ORDER BY m.measurement_date DESC, m.measurement_id DESC
    ) = 1
),
tfge AS (
    SELECT c.subject_id AS person_id,
           m.value_as_number AS tfge
    FROM cohorte c
    JOIN measurement m
      ON m.person_id = c.subject_id
     AND m.measurement_concept_id = 46236952
     AND m.value_as_number IS NOT NULL
     AND m.measurement_date BETWEEN c.cohort_start_date - INTERVAL 365 DAY
                                 AND c.cohort_start_date
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY c.subject_id
        ORDER BY m.measurement_date DESC, m.measurement_id DESC
    ) = 1
),
hemoglobina AS (
    SELECT c.subject_id AS person_id,
           m.value_as_number AS hemoglobina
    FROM cohorte c
    JOIN measurement m
      ON m.person_id = c.subject_id
     AND m.measurement_concept_id = 3000963
     AND m.value_as_number IS NOT NULL
     AND m.measurement_date BETWEEN c.cohort_start_date - INTERVAL 365 DAY
                                 AND c.cohort_start_date
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY c.subject_id
        ORDER BY m.measurement_date DESC, m.measurement_id DESC
    ) = 1
)
SELECT e.person_id,
       e.edad,
       e.hombre,
       CASE WHEN dm2.person_id IS NULL THEN 0 ELSE 1 END AS dm2_prev,
       CASE WHEN ic.person_id IS NULL THEN 0 ELSE 1 END AS ic_prev,
       CASE WHEN erc.person_id IS NULL THEN 0 ELSE 1 END AS erc_prev,
       CASE WHEN demencia.person_id IS NULL THEN 0 ELSE 1 END AS demencia_prev,
       cr.creatinina,
       al.albumina,
       tf.tfge,
       hb.hemoglobina
FROM edad_sexo e
LEFT JOIN dm2 ON dm2.person_id = e.person_id
LEFT JOIN ic ON ic.person_id = e.person_id
LEFT JOIN erc ON erc.person_id = e.person_id
LEFT JOIN demencia ON demencia.person_id = e.person_id
LEFT JOIN creatinina cr ON cr.person_id = e.person_id
LEFT JOIN albumina al ON al.person_id = e.person_id
LEFT JOIN tfge tf ON tf.person_id = e.person_id
LEFT JOIN hemoglobina hb ON hb.person_id = e.person_id
