# Included public starter corpus

`annual.csv`, `marriage.csv`, and `living.csv` are real, cleaned public-data outputs from the local Gen Z Lens project. `manifest.json` preserves that project's source URLs, download dates, coverage, and artifact checksums. Its raw-path entries refer to the original project's raw-object archive, which is not duplicated here.

`source_notes.md` describes the definitions and limitations. The sample is for trying the chatbot; it is not a claim that every column measures Gen Z specifically. National economic data is all-household context. Living with a spouse is different from marital status. Annual common-complete economic coverage ends in 2024; marriage-age coverage ends in 2025; age-specific living arrangements end in 2023 in this snapshot. All this comes from the preserved source dataset, not simulated observations.

Sources: [FRED](https://fred.stlouisfed.org/), [Census marital tables](https://www.census.gov/data/tables/time-series/demo/families/marital.html), and [Census adult living arrangements](https://www.census.gov/data/tables/time-series/demo/families/adults.html). The original providers' terms and methodology notes apply, including Freddie Mac's PMMS series notes. No provider endorsement is implied.

Only the three CSV files and source_notes.md are indexed as evidence by the sample loader. The manifest and this README stay available for provenance without filling the search results with internal index metadata.
