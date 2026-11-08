# Methodology and reading the results

## Scope

United States, national totals. Economic comparisons describe calendar periods and all-household context. They do not track specific generations' earnings or home purchases. Gen Z is treated as born 1997–2012 for labeling only; generation boundaries are a convention, not an observed variable in these tables.

## Housing and income

FRED `MSPUS` is the median sales price of **new** houses sold, reported quarterly. The dashboard takes the arithmetic mean of four quarterly medians for each complete year. That mean is not a true annual median and excludes existing-home transactions. It can change because the mix, size or location of homes sold changed.

`MEHOINUSA646N` is nominal median annual household income from Census CPS ASEC, covering all households. Home sale populations and income populations are not matched. A home-price-to-income ratio is an illustrative national indicator, not a measure of the share of Gen Z households who can buy a home.

Mortgage inputs are annual means of weekly `MORTGAGE30US` observations, requiring at least 50 observations in a past year. Freddie Mac changed PMMS methodology in November 2022. Applying its rate to a 15- or 20-year model is a controlled scenario using the same observed 30-year rate, not an observed term-specific quote.

Monthly principal and interest use fixed-rate amortization. A zero-rate loan pays principal divided by the number of months. Property tax, insurance and maintenance assumptions are percentages of home price; PMI is a percentage of loan balance, applied only below 20% down. Those percentages stay constant through the modeled history. They are not historical tax/insurance/maintenance observations. The model omits HOA fees, utilities, closing and selling costs, tax benefits and underwriting differences. Income shares are before-tax gross-income ratios, not lending decisions.

## Inflation and cost indices

`CPIAUCSL` is the seasonally adjusted all-items CPI-U. Real dollars in reference-year prices equal nominal dollars multiplied by reference-year annual CPI divided by observation-year annual CPI. The app deflates both home prices and income consistently.

Rent (`CUSR0000SEHA`), food at home (`CUSR0000SAF11`) and energy (`CPIENGSL`) are category price indices, not expenditures or median bills. Each plotted index is independently rebased to 100 in the selected baseline year. Earnings (`AHETPI`) are average hourly earnings of private production and nonsupervisory workers, not all workers, a median wage, household income or a Gen Z-specific wage.

Annual means require 12 valid monthly observations. Current-year observations are retained for inspection but excluded from annual comparisons. Historical incomplete years are also excluded. The annual comparison table uses the intersection of complete years across all economic series. No interpolation or forward-filling is performed. Latest individual releases appear separately with their observation dates so different reference periods are not silently mixed.

## Marriage and young-adult living arrangements

Census MS-2 reports estimated national median age at first marriage, for men and women. It is not a measure exclusively of Gen Z and does not follow individuals. Historical coverage contains sparse early census benchmarks and later CPS observations. Actual observation years are preserved. Consult the source notes for survey, population-control and same-sex inclusion changes; these are not harmonized away.

Census AD-3 provides living-arrangement percentages for fixed age groups **18–24** and **25–34**. Its source labels are retained:

- Living with spouse: not the same as currently married, ever married, or a marriage rate.
- Child of householder: a relationship category, not everyone who lives with parents. The source's treatment of students and household relationships matters.
- Living with partner: some older observations are unavailable. Missing observations remain missing and are not treated as zero.
- Living alone: a within-age/sex percentage.

The combined statistic weights the published men's and women's percentages by their same-year, same-age populations, which are reported in thousands. It is a calculation from rounded estimates, not a new survey statistic with its own calculated margin of error. The application does not display uncertainty intervals because these particular source tables do not supply an interval for this derived comparison.

For a year Y and ages A–B, the approximate displayed birth span is Y−B through Y−A. Birthdays can shift individual birth years by one year. The app labels overlapping generations rather than treating ages 25–34 as uniformly Gen Z. Fixed age bands help compare similar life stages but do not isolate age, cohort, and period effects.

## Revision handling and provenance

Historical Census tables can list multiple rows for one year, reflecting revisions or different population controls/questionnaires. The parser retains the first publisher-listed row per year and sex. It stores the original row label and counts removed alternatives in `quality.json`. This deterministic policy does not make the whole history methodologically uniform.

Raw files are immutable and named by SHA-256 digest. A processed run records each source URL, retrieval timestamp, units, observation coverage, status, and raw-file digest. Each CSV artifact also has a digest. The dashboard verifies artifact hashes before displaying data. A new processed run becomes active only when its full build passes validation. Fetch timestamps are download times, not observation dates or provider release dates.

## Interpretation

The dashboard is descriptive. It cannot show that a change in house prices caused a change in marriage behavior, establish differences between otherwise-identical generations, predict an individual's life, or substitute for region-specific data. Use the same-age tables, dates, source definitions, scenario assumptions and quality report when discussing the results.
