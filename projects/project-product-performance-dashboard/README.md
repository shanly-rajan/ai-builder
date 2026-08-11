# Project & Product Performance Dashboard

A standalone Streamlit experiment that connects engineering delivery, investment,
testing, release quality, product adoption, revenue, break-even, and profitability.
Every project, person, product, cost, and transaction in the included dataset is
fictional and generated deterministically.

## What the dashboard answers

- Did we deliver what we committed to, and was it early, on time, or late?
- What did the engineering work cost compared with its estimate?
- Which initiatives meet their transparent release criteria?
- Did released capabilities achieve adoption and generate revenue?
- Which products recovered their attributed engineering investment?

The dashboard deliberately avoids lines of code, commit counts, ticket counts,
individual velocity, and other misleading developer-productivity measures.

## Quick start

Python 3.11 or 3.12 is recommended.

```bash
cd projects/project-product-performance-dashboard
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

## Development

```bash
python -m pip install -r requirements-dev.txt
pytest
ruff check .
```

Regenerate the deterministic fixture with:

```bash
python scripts/generate_sample_data.py
```

The full automated suite includes pure calculation tests, CSV/data-integrity tests,
generator reproducibility tests, and Streamlit page-rendering smoke tests.

## Dashboard pages

- **Executive overview** — the required delivery, release, investment, revenue,
  profit, and break-even portfolio KPIs plus prioritized exceptions.
- **Project performance** — planned versus actual timelines, effort/cost variance,
  team/category comparisons, and project-level evidence.
- **Testing & quality** — test execution and pass rates, applicable category
  coverage, defects, UAT, release readiness, and release exceptions.
- **Product performance** — customer adoption, transaction growth, revenue,
  operating cost, monthly profit, margin, and product rankings.
- **Break-even & ROI** — investment composition, cumulative financial curves,
  first-crossing markers, ROI, and product comparison.

Project filters and product filters are intentionally separate. A team selection can
scope delivery investment, but it never implies that product revenue belongs to that
team.

## Sample dataset

The committed fixture in `data/sample/` is generated with seed `20260811` and a
fixed reporting date of 31 December 2025. It contains:

- 24 projects across five fictional engineering teams and ten role types.
- 10 products with 136 monthly history records across a 24-month window.
- 187 role allocations, 48 additional engineering cost items, 712 test cases,
  18 defects, 24 release assessments, and 36 project/product mappings.
- Designed early, on-time, delayed, active-overdue, under/over-budget, clean,
  blocked, exception-release, profitable, approaching, new, and underperforming
  scenarios.

All committed CSVs are reproduced byte-for-byte by the generator and checked by the
integration suite.

## Metric conventions

- Durations use inclusive calendar days. Final schedule variance is unavailable for
  incomplete work; active work receives a separate overdue-days measure.
- On-time delivery includes early and exactly-on-time completed projects. Cancelled
  projects keep their incurred cost but leave the delivery-rate denominator.
- Actual engineering cost means cost to date until completion. It includes fictional
  role cost, engineering infrastructure, and external engineering/integration cost.
- A blocked test counts as executed but unsuccessful. Zero denominators display as
  `N/A` rather than zero or infinity.
- Release readiness is a transparent gate: all applicable required tests pass, UAT
  passes where applicable, and no open critical/high release blocker remains.
- Adoption is active customers divided by eligible customers. Product revenue is
  never attributed to a project, team, or individual.
- Break-even is the first observed month whose cumulative profit is non-negative;
  months to break-even are counted inclusively from the launch month.

## Architecture

Streamlit pages depend on presentation helpers and pure domain services. Domain
services operate on validated canonical data and never import Streamlit. The sample
CSV source is one implementation of a data-source contract that future Jira, CI/CD,
test-management, transaction, finance, or cloud-cost adapters can implement.

```text
Streamlit pages -> UI/view helpers -> pure metric services
                                      |
                               canonical data bundle
                                      ^
                              CSV data-source adapter
```

The canonical `DashboardDataBundle` contains typed Pandas DataFrames. New adapters
must normalize their source records to that contract and pass the same cross-table
validation before business calculations run. Pages never read CSVs directly, and
domain services never import Streamlit.

## Financial scope

The first version uses a deliberately simple, single-currency model:

```text
initial investment = allocated engineering cost + launch cost + setup cost
monthly profit = revenue - operating cost
cumulative profit = cumulative revenue - cumulative operating cost - initial investment
ROI = cumulative profit / initial investment
```

It excludes taxes, financing, depreciation, foreign exchange, discounted cash flow,
and NPV. Later enhancement costs are part of the current investment basis; a dated
reinvestment ledger is a future extension for preserving historical payback exactly.

## Data and privacy

The committed sample data contains aggregate fictional information only. It contains
no real employees, salaries, merchants, customers, credentials, internal URLs, or
company financials. The fixed seed and as-of date make results reproducible.
