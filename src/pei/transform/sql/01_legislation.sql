-- Clean legislative tables from raw Congress.gov JSON. Input: raw_bills (one JSON document per bill).

CREATE OR REPLACE TABLE bills AS
SELECT
    bill_id,
    (doc -> 'bill' ->> 'congress')::INT AS congress,
    lower(doc -> 'bill' ->> 'type') AS bill_type,
    (doc -> 'bill' ->> 'number')::INT AS bill_number,
    upper(doc -> 'bill' ->> 'type') || ' ' || (doc -> 'bill' ->> 'number') AS label,
    doc -> 'bill' ->> 'title' AS title,
    doc -> 'bill' ->> 'originChamber' AS origin_chamber,
    (doc -> 'bill' ->> 'introducedDate')::DATE AS introduced_date,
    doc -> 'bill' -> 'policyArea' ->> 'name' AS policy_area,
    (doc -> 'bill' -> 'latestAction' ->> 'actionDate')::DATE AS latest_action_date,
    doc -> 'bill' -> 'latestAction' ->> 'text' AS latest_action_text,
    (doc -> 'bill' ->> 'updateDateIncludingText')::TIMESTAMP AS official_update_at,
    doc -> 'bill' ->> 'legislationUrl' AS congress_gov_url,
    doc -> 'bill' -> 'sponsors' -> 0 ->> 'bioguideId' AS sponsor_bioguide,
    fetched_at::TIMESTAMP AS fetched_at,
    is_candidate,
    sample_stratum
FROM raw_bills;

CREATE OR REPLACE TABLE actions AS
SELECT
    r.bill_id,
    (a.value ->> 'actionDate')::DATE AS action_date,
    a.value ->> 'text' AS action_text,
    a.value ->> 'type' AS action_type,
    a.value ->> 'actionCode' AS action_code,
    a.value -> 'sourceSystem' ->> 'name' AS source_system
FROM raw_bills AS r, json_each(r.doc -> 'actions') AS a;

CREATE OR REPLACE TABLE recorded_vote_refs AS
SELECT DISTINCT
    r.bill_id,
    v.value ->> 'chamber' AS chamber,
    (v.value ->> 'congress')::INT AS congress,
    (v.value ->> 'sessionNumber')::INT AS session,
    (v.value ->> 'rollNumber')::INT AS roll,
    v.value ->> 'url' AS primary_url,
    (v.value ->> 'date')::TIMESTAMP::DATE AS vote_date
FROM raw_bills AS r,
    json_each(r.doc -> 'actions') AS a,
    json_each(a.value -> 'recordedVotes') AS v;

CREATE OR REPLACE TABLE text_versions AS
SELECT
    r.bill_id,
    (t.value ->> 'date')::TIMESTAMP::DATE AS version_date,
    t.value ->> 'type' AS version_type,
    t.value -> 'formats' -> 0 ->> 'url' AS url
FROM raw_bills AS r, json_each(r.doc -> 'text') AS t;

CREATE OR REPLACE TABLE summaries AS
SELECT
    r.bill_id,
    (s.value ->> 'updateDate')::TIMESTAMP AS updated_at,
    s.value ->> 'actionDesc' AS version_desc,
    regexp_replace(s.value ->> 'text', '<[^>]+>', ' ', 'g') AS summary_text
FROM raw_bills AS r, json_each(r.doc -> 'summaries') AS s;

CREATE OR REPLACE TABLE latest_summaries AS
SELECT bill_id, summary_text, version_desc
FROM summaries
QUALIFY row_number() OVER (PARTITION BY bill_id ORDER BY updated_at DESC NULLS LAST) = 1;

CREATE OR REPLACE TABLE bill_committees AS
SELECT
    r.bill_id,
    c.value ->> 'chamber' AS chamber,
    c.value ->> 'name' AS committee_name,
    c.value ->> 'systemCode' AS committee_code
FROM raw_bills AS r, json_each(r.doc -> 'committees') AS c;

-- Stage comes from official action records. The order runs furthest stage first.
CREATE OR REPLACE TABLE bill_stage AS
WITH flags AS (
    SELECT
        b.bill_id,
        bool_or(a.action_type = 'BecameLaw' OR a.action_text ILIKE 'Became Public Law%') AS is_law,
        bool_or(a.action_type = 'Veto' OR a.action_text ILIKE 'Vetoed by President%') AS is_vetoed,
        bool_or(a.action_type = 'President') AS to_president,
        bool_or(a.action_text ILIKE 'Passed House%' OR a.action_text ILIKE 'Passed/agreed to in House%'
            OR a.action_text ILIKE 'On passage Passed%'
            OR a.action_text ILIKE 'On motion to suspend the rules and pass%Agreed to%'
            OR a.action_text ILIKE 'Agreed to in House%') AS passed_house,
        bool_or(a.action_text ILIKE 'Passed Senate%' OR a.action_text ILIKE 'Passed/agreed to in Senate%'
            OR a.action_text ILIKE 'Agreed to in Senate%') AS passed_senate,
        bool_or(a.action_text ILIKE '%reported%' AND a.action_type IN ('Committee', 'Calendars'))
            AS reported
    FROM bills AS b
    LEFT JOIN actions AS a USING (bill_id)
    GROUP BY b.bill_id
)
SELECT
    bill_id,
    CASE
        WHEN is_law THEN 'became_law'
        WHEN is_vetoed THEN 'vetoed'
        WHEN to_president THEN 'to_president'
        WHEN passed_house AND passed_senate THEN 'passed_both'
        WHEN passed_house OR passed_senate THEN 'passed_one_chamber'
        WHEN reported THEN 'reported_from_committee'
        ELSE 'introduced'
    END AS stage,
    CASE
        WHEN is_law THEN 6
        WHEN is_vetoed THEN 5
        WHEN to_president THEN 4
        WHEN passed_house AND passed_senate THEN 3
        WHEN passed_house OR passed_senate THEN 2
        WHEN reported THEN 1
        ELSE 0
    END AS stage_rank
FROM flags;
