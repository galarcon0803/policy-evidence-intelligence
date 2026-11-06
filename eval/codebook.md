# Labeling codebook

Label each bill **before seeing any classifier output**. These labels are the ground truth for the
classifier's precision and recall, so please go with your own judgment, not what you expect a model
to say. Don't use an AI tool for labeling.

## How to label
Open `eval/labels_to_fill.csv`. It has about 60 bills. Use the title and summary in the sheet, and
follow the Congress.gov link if they aren't enough. This should take about a minute per bill.

For each of the four pillar columns, enter:

- **1** if the bill is **relevant**: a main subject, or a substantive provision the policy team would
  need to read.
- **0** if it is not: no connection, or only a passing mention or indirect effect.

Each bill gets a 0 or 1 in all four columns. A bill can be relevant to several pillars, or to none.
Most bills should be 0 on most pillars. Use `notes` for anything you found hard to call, and leave a
cell blank only if you truly can't tell. Blanks are excluded from scoring and reported.

Save the finished file as `eval/labels.csv`.

## Pillars

| Column | Pillar | Relevant topics |
|---|---|---|
| `electricity_affordability` | Electricity & affordability | Residential rate impacts, cost allocation for large loads, grid and transmission investment, energy bill assistance, electricity reliability or supply policy |
| `data_centers_communities` | Data centers & communities | Data center siting, permitting, local tax and jobs, water, noise, local restrictions, community effects of computing infrastructure |
| `education_learning` | Education & learning | AI or technology in schools and colleges, learning outcomes, ed tech procurement, assessment, student data, AI or digital literacy |
| `jobs_skills` | Jobs & skills | Occupational task change, automation and displacement, AI and technology skills, hiring, broad workforce programs |

## Boundary rules
The classifier follows these same rules, so both are held to one definition.

- **Judge the subject, whether or not AI is mentioned.** A bill on residential electricity rates is
  relevant even if it never mentions AI.
- **Workforce:** a bill limited to one occupation or sector with no link to technology or automation
  (such as loan repayment for nurses) is **0**. A broad workforce program is **1**.
- **Schools:** a school bill unrelated to technology, learning measurement, or student data (such as
  school meals or safety drills) is **0**.
- **Energy:** a bill about fuel extraction or vehicles, with no electricity rate or grid provision, is **0**.
- **General AI bills:** not automatically relevant. Mark only the pillars the bill actually addresses.

## Why the sheet includes off-topic bills
About a third of the sheet was rejected by the title keyword filter. They measure what that filter
misses, so expect many of them to be 0 across the board. If one is relevant, that's a useful finding.
