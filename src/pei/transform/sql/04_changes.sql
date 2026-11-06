-- Change detection, as of a baseline date held in the one-row table change_baseline.
-- Every change comes from a dated official record, so the same query works for any baseline.
-- Types follow the brief: new, new action, new text version, vote held.

CREATE OR REPLACE TABLE bill_changes AS
WITH base AS (SELECT baseline_date FROM change_baseline),
new_bills AS (
    SELECT bill_id, 'new' AS change_type, introduced_date AS change_date,
        'Introduced' AS detail
    FROM bills, base
    WHERE introduced_date > baseline_date
),
new_actions AS (
    SELECT bill_id, 'new_action' AS change_type, action_date AS change_date,
        action_text AS detail
    FROM actions, base
    WHERE action_date > baseline_date
),
new_text AS (
    SELECT bill_id, 'new_text_version' AS change_type, version_date AS change_date,
        version_type AS detail
    FROM text_versions, base
    WHERE version_date > baseline_date
),
votes AS (
    SELECT bill_id, 'vote_held' AS change_type, vote_date AS change_date,
        chamber || ' roll call ' || roll AS detail
    FROM recorded_vote_refs, base
    WHERE vote_date > baseline_date
)
SELECT DISTINCT * FROM (
    SELECT * FROM new_bills
    UNION ALL SELECT * FROM new_actions
    UNION ALL SELECT * FROM new_text
    UNION ALL SELECT * FROM votes
);
