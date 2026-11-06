-- Members, committee assignments, and documented evidence. No predictions anywhere in this file.

CREATE OR REPLACE TABLE members AS
SELECT DISTINCT ON (bioguide_id)
    bioguide_id,
    name,
    party,
    state,
    chamber
FROM raw_members
ORDER BY bioguide_id, chamber;

CREATE OR REPLACE TABLE committee_assignments AS
SELECT
    bioguide AS bioguide_id,
    committee_code,
    committee_name,
    title
FROM raw_committee_membership;

CREATE OR REPLACE TABLE cosponsors AS
SELECT
    r.bill_id,
    c.value ->> 'bioguideId' AS bioguide_id,
    (c.value ->> 'sponsorshipDate')::DATE AS sponsorship_date,
    (c.value ->> 'isOriginalCosponsor')::BOOLEAN AS is_original,
    c.value ->> 'sponsorshipWithdrawnDate' AS withdrawn_date
FROM raw_bills AS r, json_each(r.doc -> 'cosponsors') AS c;

-- One row per member, per recorded vote. Senate rows come from Voteview, labeled secondary.
CREATE OR REPLACE TABLE member_votes AS
SELECT
    ref.bill_id,
    'House' AS chamber,
    ref.session,
    ref.roll,
    v.bioguide_id,
    v.cast_vote,
    v.vote_question,
    v.evidence_type,
    ref.vote_date,
    ref.primary_url AS source_url,
    'primary: House Clerk' AS source_tier
FROM recorded_vote_refs AS ref
JOIN raw_house_votes AS v
    ON ref.chamber = 'House' AND ref.congress = v.congress
    AND ref.session = v.session AND ref.roll = v.roll
UNION ALL
SELECT
    ref.bill_id,
    'Senate' AS chamber,
    ref.session,
    ref.roll,
    v.bioguide_id,
    v.cast_vote,
    v.vote_question,
    v.evidence_type,
    ref.vote_date,
    ref.primary_url AS source_url,
    'secondary: Voteview (UCLA)' AS source_tier
FROM recorded_vote_refs AS ref
JOIN raw_senate_votes AS v
    ON ref.chamber = 'Senate' AND ref.congress = v.congress
    AND ref.session = v.session AND ref.roll = v.roll;

CREATE OR REPLACE TABLE member_evidence AS
SELECT
    b.sponsor_bioguide AS bioguide_id,
    b.bill_id,
    'sponsor' AS evidence_type,
    NULL AS vote_cast,
    b.introduced_date AS evidence_date,
    b.congress_gov_url AS source_url,
    'primary: Congress.gov' AS source_tier
FROM bills AS b
WHERE b.sponsor_bioguide IS NOT NULL
UNION ALL
SELECT
    c.bioguide_id,
    c.bill_id,
    'cosponsor',
    NULL,
    c.sponsorship_date,
    b.congress_gov_url,
    'primary: Congress.gov'
FROM cosponsors AS c
JOIN bills AS b USING (bill_id)
WHERE c.withdrawn_date IS NULL
UNION ALL
SELECT
    bioguide_id,
    bill_id,
    evidence_type,
    cast_vote,
    vote_date,
    source_url,
    source_tier
FROM member_votes;
