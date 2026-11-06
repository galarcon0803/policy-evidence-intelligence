# Data sources and licenses

The files in this folder are derived from the public sources below. This notice covers the data, and
the project's code is separate.

| File | Source | Terms |
|---|---|---|
| `atlas_state.parquet` | [IM3 Open Source Data Center Atlas](https://data.msdlive.org/records/qxpk8-yae09) v2026.11.02, derived from [OpenStreetMap](https://www.openstreetmap.org/copyright) | **Open Database License (ODbL) 1.0.** This state-level aggregate is shared under the same license. © OpenStreetMap contributors |
| `epoch_us_sites.parquet` | [Epoch AI, AI data centers](https://epoch.ai/data/ai-data-centers), retrieved November 2026 | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| `aei_state.parquet` | [Anthropic Economic Index](https://huggingface.co/datasets/Anthropic/EconomicIndex), release 2026-06-26 | CC BY, per the release's documentation |
| `aei_job_exposure.parquet` | [Anthropic Economic Index](https://huggingface.co/datasets/Anthropic/EconomicIndex), labor market impacts | MIT, per the dataset's repository tag |
| `state_year_panel.parquet` | [US Energy Information Administration](https://www.eia.gov/opendata/) | US government data |
| Bill, action, cosponsor, and vote tables | [Congress.gov](https://www.congress.gov/), [House Clerk](https://clerk.house.gov/), [Federal Register](https://www.federalregister.gov/) | US government data |
| Senate vote rows, where present | [Voteview](https://voteview.com/) (UCLA) | The site states no data license. Only rows tied to tracked bills are included, credited here as a secondary source. Will be removed on request |
| `committee_assignments.parquet` | [congress-legislators](https://github.com/unitedstates/congress-legislators) | CC0 |

This project is independent, and none of these sources endorses it. This is a good-faith summary of
each source's terms, and is not legal advice.
