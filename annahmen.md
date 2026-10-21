# Assumptions and audit trail

Every figure used in the model, with its source and page. Page numbers refer to the PDF of the respective annual report (printed page = PDF page unless stated otherwise). Amounts in € million unless stated otherwise.

# Model-wide assumptions

| Assumption | Value | Unit | Source / rationale |
|---|---|---|---|
| Average carbon price 2025 | 73 | €/t | Volume-weighted average EUA price 2025: €73.43/t (Instrat, EU ETS 2025 summary) |
| Carbon price 2030 (default) | 100 | €/t | Own assumption, adjustable in the app |
| Carbon price increase after 2030 | +5.40 | €/t per year | Own extrapolation (2050: ~208 €/t) |
| Phase-out of free allocation | see `src/modell.py` | | Current law vs. Commission proposal COM(2026) 616 (not adopted) |
| Emissions after 2030 | linear path | | From the 2030 level towards the 2050 target, scaled by "climate target achieved" |
| Terminal value | perpetuity | | Cost 2050 after tax ÷ WACC |
| Pass-through to customers (default) | 40 | % | Historically 20–40 % for cement (Öko-Institut/CE Delft 2015); likely higher with CBAM |
| Enterprise value | | | Market capitalisation + net financial debt + pension provisions (same formula for all companies) |

# Thyssenkrupp (fiscal year 2024/2025, balance sheet date 30 Sep 2025)

Source: annual report 2024/2025 (German). Auditor: KPMG.

| Figure | Value | Unit | Page |
|---|---|---|---|
| Revenue | 32,837 | €m | 2, 329 |
| Adjusted EBIT | 640 | €m | 2 |
| EBIT | 76 | €m | 329 |
| EBITDA | 1,490 | €m | 329 |
| Free cash flow before M&A | 363 | €m | 2, 330 |
| Net financial assets (net cash) | 4,862 | €m | 2, 330 |
| Pension provisions | 5,298 | €m | 329 |
| Market capitalisation 30 Sep 2025 | 7,271 | €m | 2 |
| Tax rate Germany (instead of effective 48.7 %) | 31.6 | % | 321 |
| WACC after tax, Steel Europe (impairment test Q4) | 7.6 | % | 259 (Q1: 8.0 %, p. 258) |
| WACC per value management (tkVA) group / Steel Europe, probably before tax | 11.0 / 12.0 | % | 48 |
| Scope 1 gross | 19.8 | Mt CO₂e | 123 |
| Thereof covered by internal carbon price | ~16 | Mt CO₂e | 124 |
| Internal carbon price | up to ~150 (2035), ~250 (2045) | €/t | 124 |
| Target Scope 1+2 | 21.0 → 15.6 Mt by 2029/30 | | 123 |
| Climate target steel | −30.1 % per t hot strip by 2030 vs. 2018 | | 118 |
| Share in HKM (joint operation) | 50 | % | 268 |
| Shares outstanding | 622.5 | million | 17 |

## Model decisions Thyssenkrupp

| Decision | Rationale |
|---|---|
| Tax rate 31.6 % instead of effective 48.7 % | Effective rate distorted by valuation allowances on deferred taxes (p. 321) |
| WACC 7.6 % (Q4 test), not 8.0 % (Q1 test) | Same reporting date as all other figures |
| Enterprise value incl. pensions | Pensions are economically debt-like |
| Annual reduction 5.8 % until 2030 | (15.6 / 21.0)^(1/5) − 1; depends heavily on the DR plant in Duisburg |
| Spin-off of Steel Europe as a scenario | Sale to Jindal called off in May 2026; target: standalone with a minority stake |

## Market value

| Figure | Value | Unit | Source |
|---|---|---|---|
| Market capitalisation | 8,634 | €m | finanzen.net, 20 Oct 2026: 622.5m shares × €13.87 |
| Enterprise value (market cap + pensions − net cash) | 9,070 | €m | calculated |

## EU ETS matching

Boundary as in the report: consolidation scope of financial reporting, HKM pro rata 50 % (p. 120). Matching via a fixed table in `src/ets_thyssenkrupp.py`, because some registry accounts are anonymised.

| Figure | Value | Unit | Source |
|---|---|---|---|
| Emissions 2025 (incl. 50 % HKM) | 17.80 | Mt | EU registry |
| Free allocation 2025 (incl. 50 % HKM) | 18.61 | Mt | EU registry |
| Coverage 2025 | 105 | % | calculated |
| Reconciliation: ETS 2024 vs. reported Scope 1 | 19.48 vs. 19.8 (−1.6 %) | Mt | p. 123 (the report uses ETS calendar year 2024) |

Uncertain assignments (plausibility-checked through reconciliation, not proven): coke plant Schwelgern (account 83), power plant Hamborn unit 5, boiler plant Hamborn, "Glocke Duisburg" (account 71, HKM).
Not assigned: small Duisburg installations with about 0.3 Mt (e.g. "Stahlwerk Duisburg").
Note: free allocation sits with the steelworks, emissions with the power plants that burn its waste gases – therefore the evaluation is per site.

# AI extraction (Gemini Flash)

| Run | Report | Accuracy | Audit trail | Note |
|---|---|---|---|---|
| 1–2 | Pilot report (not published) | 4/7 → 7/7 | 7/7 | Prompt refined on the same report – risk of overfitting |
| 3 | Thyssenkrupp 2024/2025 | 6/7 | 6/7 | Out-of-sample test with unchanged code. Pensions: AI took 5,162 (p. 278) instead of 5,298 (balance sheet, p. 329). WACC: correct value 7.6 % from Q4 despite four candidate values; quote check failed because of PDF text formatting. Results: `ergebnisse/ki_extraktion_thyssenkrupp.csv` |

# Company scenarios (all companies)

Adjustable in the app under "Company scenarios". Default values = base case; the result does not change.

| Scenario | Default | Effect in the model | Example |
|---|---|---|---|
| Delay of emission reductions | 0 years | Emissions stay at the 2025 level for n years, then the path runs shifted by n years; the 2050 target is not fully reached by 2050 | DR plant in Duisburg is delayed |
| Share of emissions with a carbon price | 100 % | Emissions and free allocation × share | Plants outside the EU; already reflected for Thyssenkrupp (17.8 Mt EU ETS) |
| Spin-off: share of emissions | 0 % | Emissions and free allocation × (1 − share) | Steel Europe as a standalone company |
| Spin-off: share of enterprise value | 0 % | Enterprise value × (1 − share), max. 90 % | Own assumption, not derived from the report |

Check (20 Oct 2026): with default values, the annual table, Monte Carlo and tornado are identical to the results before this change.

# Ranking (all companies, common assumptions)

Shown on the page "Ranking". Purpose: compare carbon exposure across companies, not to value each company in detail.

| Assumption | Value | Rationale |
|---|---|---|
| Emissions until 2030 | constant at 2025 level | Same starting point for all; company plans (e.g. electric arc furnaces) excluded |
| Discount rate | 8 % | Common rate for all companies (adjustable on the page) |
| Tax rate | 25 % | Common rate |
| Pass-through, carbon price, CBAM path | as in the main model (40 %, €100/t, current law) | Adjustable on the page |
| Enterprise value | market cap (Oct 2026) + net financial debt + pensions | Same formula as the main model |
| Currency | ECB reference rates 31 Dec 2025 (USD 1.1750, CHF 0.9314, SEK 10.8215, NOK 11.8430 per €) | Balance sheet date |

| Company | Sector | Auditor | EU ETS 2025 (Mt) | Coverage | Market cap (€m) | Net financial debt (€m) | Pensions (€m) |
|---|---|---|---|---|---|---|---|
| Thyssenkrupp | Steel | KPMG | 17.80 | 105 % | 8,634 | −4,862 | 5,298 |
| Salzgitter | Steel | EY | 8.84 | 93 % | 2,574 | 954 | 1,408 |
| voestalpine | Steel | Deloitte | 12.26 | 77 % | 7,817 | 1,300 | 817 |
| SSAB | Steel | EY | 8.57 | 91 % | 9,270 | −1,072 | n/a |
| ArcelorMittal | Steel | EY | 28.31 | 133 % | 42,410 | 6,750 | 2,150 |
| Holcim | Cement | EY | 11.96 | 109 % | 38,040 | 4,064 | 283 |
| Norsk Hydro | Aluminium | KPMG | 1.85 | 89 % | 14,050 | 1,537 (adjusted, incl. pensions) | – |

Detailed sources per figure: `src/ranking_daten.json`. Installation list: `ergebnisse/ranking_anlagen.csv`. Figures marked [prüfen] there still need to be verified.

Data decisions:
- Salzgitter: 49 % of emissions with uncertain assignment (power plant Hallendorf; 30 % share in HKM).
- Thyssenkrupp: the ranking uses common assumptions (8 % WACC, no reductions until 2030) and therefore shows a higher share (≈71 %) than the detailed model (48 %).
- ArcelorMittal: coverage of 133 % partly reflects allowances for waste gases delivered to third-party power plants; exposure probably understated. German sites (Bremen, Eisenhüttenstadt, Duisburg) matched via anonymised accounts – uncertain.
- Companies are only published if their auditor could be verified and is not the author's employer.
