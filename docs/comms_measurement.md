# Measuring policy communications: a design

*Design only. Nothing here has been built, and it contains no results. Independent proposal, not
affiliated with or endorsed by Anthropic. Sample sizes and thresholds are starting points to set
with a power calculation, and they are not findings.*

## The questions
Measurement should separate four things that are often blended into one "reach" number:

| Question | Measure | Method |
|---|---|---|
| Was the research **represented accurately**? | Share of coverage that states findings and caveats correctly | Content analysis |
| Did the **right audience** see it? | Exposure among target audiences, not impressions | Panels, placement data |
| Did they **understand** it? | Correct answers on what it does and doesn't show | Comprehension survey |
| Did it **change** beliefs or actions? | Effect relative to a credible comparison | Randomized or quasi-experimental tests |

## 1. Content analysis: accuracy of coverage
Before publication, the authors write down a **claims sheet**: 5 to 10 findings, each with its caveats
and the most likely misreading. This fixes the standard before any coverage exists.

- **Sample:** all coverage from a defined outlet list, plus a random sample of the rest, over a fixed
  window.
- **Coding:** for each claim, whether it is stated accurately, overstated, understated, or omitted,
  and whether the caveat appears.
- **Reliability:** two human coders on a subset, reporting Cohen's kappa, before anyone relies on the
  codes. A model can assist with coding at scale once validated against those human codes, with the
  error rate reported, as this prototype does for bill classification.
- **Reporting:** accuracy by claim and by outlet type, so that a claim people repeatedly misread gets
  fixed at the source next time.

## 2. Audience surveys: comprehension
- **Pre/post with randomization:** randomly show target respondents the brief or a neutral placebo text,
  then ask the same comprehension and belief items. This separates what the piece teaches from who
  chose to read it.
- **Comprehension items:** factual questions drawn from the claims sheet, including one that checks the
  key limitation. For example: "Does this study show whether a specific utility's rates rose?"
- **Audience:** a staff and policy-professional panel if one can be recruited, plus a general sample.
  Report them separately, since elite panels are small and opt-in.
- **Guard against false confidence:** a rise in belief is not a success if comprehension falls. A piece
  that persuades readers of something it doesn't show counts as a failure.

## 3. Paid media: incrementality
Platform-reported conversions overstate effect, because ads go to people already likely to act.

- **Geographic holdout (default):** match media markets into pairs on past outcomes, then randomly
  assign one in each pair to run the campaign. Compare with difference-in-differences and randomization
  inference. Geographic spillover, and few markets, are the main risks.
- **Platform conversion lift**, where offered, as a second read. Treat the platform as an interested
  party and check it against the holdout.
- **Outcomes, in order of value:** verified actions (such as public comments or event signups), brand
  and issue survey lift, then site engagement. Impressions are a delivery check and never an outcome.
- **Ethics and compliance:** follow disclosure rules for political and issue ads. Review any targeting
  with counsel, and don't target individuals on sensitive traits.

## 4. Public affairs campaigns: contribution, not attribution
Legislative outcomes have many causes and few observations, so claiming a causal effect is rarely
credible. Report documented contribution instead:

- **Pre-specified trace evidence:** whether a report is cited in hearings, bill text, or agency dockets,
  which can be read from the same public sources this prototype already ingests.
- **Staggered engagement:** where outreach rolls out over time, compare early and later offices, and
  say plainly that selection limits the conclusion.
- **Report the denominator.** Show citations alongside how many relevant proceedings did not cite it.

## Common rules
- **Pre-register** the primary outcome, comparison, and sample before each campaign.
- **Publish null results internally** at the same prominence as wins.
- **Keep definitions in the metrics registry,** with the same fields as other metrics, so a comms
  number is governed like any other externally shared number.

## Proposed metrics (schema only, no data)
`claim_accuracy_rate`, `caveat_retention_rate`, `comprehension_lift`, `geo_lift_verified_actions`,
`proceedings_citing_rate`. Each would need a registry entry, and all would need data this prototype
doesn't have.
