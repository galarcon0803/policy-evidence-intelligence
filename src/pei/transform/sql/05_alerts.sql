-- Alerts: tracked bills whose status changed since the baseline, ranked by pillar relevance.
-- A bill appears once per relevant pillar, since the digest and filters are organized by pillar.

CREATE OR REPLACE TABLE alerts AS
WITH change_rollup AS (
    SELECT
        bill_id,
        max(change_date) AS latest_change,
        count(*) AS change_count,
        bool_or(change_type = 'vote_held') AS has_vote,
        bool_or(change_type = 'new') AS is_new,
        bool_or(change_type = 'new_text_version') AS has_new_text,
        string_agg(DISTINCT change_type, ', ' ORDER BY change_type) AS change_types
    FROM bill_changes
    GROUP BY bill_id
),
latest AS (
    SELECT bill_id, detail AS latest_detail, change_type AS latest_type
    FROM bill_changes
    QUALIFY row_number() OVER (
        PARTITION BY bill_id
        ORDER BY change_date DESC,
            CASE change_type
                WHEN 'vote_held' THEN 0
                WHEN 'new_text_version' THEN 1
                WHEN 'new_action' THEN 2
                ELSE 3
            END,
            detail
    ) = 1
)
SELECT
    p.pillar,
    p.bill_id,
    b.label,
    b.title,
    b.congress_gov_url,
    p.relevance,
    p.rationale,
    s.stage,
    s.stage_rank,
    c.change_types,
    c.change_count,
    c.latest_change,
    l.latest_detail,
    c.has_vote,
    c.is_new,
    c.has_new_text,
    row_number() OVER (
        PARTITION BY p.pillar
        ORDER BY p.relevance DESC, c.has_vote DESC, s.stage_rank DESC, c.latest_change DESC, p.bill_id
    ) AS pillar_rank
FROM bill_pillars AS p
JOIN change_rollup AS c USING (bill_id)
JOIN latest AS l USING (bill_id)
JOIN bills AS b USING (bill_id)
JOIN bill_stage AS s USING (bill_id)
WHERE p.is_relevant;
