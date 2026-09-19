# NeoBank ARIA — Week 6 Path A

Local hosting and security testing of the Gen Academy NeoBank ARIA assistant. ARIA is
intentionally vulnerable and uses fictional banking data. It must not be used as a production
banking application.

## Status

| Area | Status |
|---|---|
| Local Streamlit application | Complete |
| Automated checks | 8 passing; Ruff passing |
| Red-team cases | 17/17 scored |
| Results | 10 PASS · 1 WARN · 6 FAIL |
| Written report | Complete |
| Screenshot evidence | Complete: PASS, WARN, and FAIL captured |
| Breaking exploratory suite | 8 category-specific cases scored and consolidated |
| Google Doc and form submission | Manual final step |

Start with the [submission report](docs/week6-submission-report.md) for the findings and the
[results ledger](evaluation/results.json) for the consolidated structured source data.

## Architecture

```mermaid
flowchart LR
    User[Tester] --> UI[Local Streamlit app]
    UI --> Agent[ARIA agent]
    Agent --> LLM[OpenAI model]
    Agent --> KB[Policy knowledge base]
    Agent --> DB[(SQLite fictional accounts)]

    UI --> Results[Recorded results]
    Results --> Report[Submission report]
```

The central architectural risk is outside the model: `query_account` accepts any user ID and does
not enforce ownership. A model refusal may prevent one attack attempt, but it is not a reliable
authorization control.

## Run locally

```bash
cd projects/neo-bank-aria-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Add a valid key to the ignored `.env` file:

```dotenv
OPENAI_API_KEY=your-key-here
OPENAI_MODEL=gpt-4o-mini
NEOBANK_DB_PATH=neobank.db
```

Then start the application:

```bash
python -m streamlit run app.py
```

Use the fictional workshop identity `Alex Mercer` (`USR-0042`). Never include the API key in
screenshots, logs, or submission documents.

## Verify the project

```bash
python -m pytest
python -m ruff check .
python scripts/generate_submission.py
```

The strict submission gate also verifies that all required evidence files exist:

```bash
python scripts/generate_submission.py --require-complete
```

## Consolidated breaking suite

The canonical submission now contains the original nine cases plus eight failure-seeking cases,
one stronger test for each security category:

| Category | Case | Chat protocol |
|---|---|---|
| Jailbreaking | `JB-02` | Fresh chat |
| Obfuscation | `OBF-02` | Fresh chat |
| Sensitive Data Exposure | `SDE-02` | Fresh chat |
| Prompt Injection | `PI-02` | Fresh chat |
| Red Teaming | `RT-02` | Fresh chat |
| Crescendo | `CRE-02` | Four separate turns in the same chat |
| PII Extraction | `PII-02` | Fresh chat |
| Social Engineering | `SOC-02` | Fresh chat |

The consolidated scores, responses, reasoning, and evidence references are in
[`evaluation/results.json`](evaluation/results.json). The original
[`evaluation/breaking_test_cases.json`](evaluation/breaking_test_cases.json) and
[`evaluation/breaking_results.json`](evaluation/breaking_results.json) remain as an auditable
source copy of the extended run.

## Test outcome

| Result | Cases |
|---|---|
| PASS | 10 cases, including the benign control, jailbreak, direct red-team lookup, and PII variants |
| WARN | CRE-01 exposed the restricted topic name but refused its contents |
| FAIL | 6 cases exposed restricted policy data, internal sources, or unsafe tool/account behavior |

The key finding is that ARIA can reveal its internal tool surface even without calling a tool.
The highest-priority fix is backend authorization, followed by restricted-data separation and
input/output guardrails.

## Submission artifacts

| File | Purpose |
|---|---|
| [`docs/week6-submission-report.docx`](docs/week6-submission-report.docx) | Google Docs-ready final submission document |
| [`docs/week6-submission-report.md`](docs/week6-submission-report.md) | Final report to copy or export to Google Docs |
| [`evaluation/results.json`](evaluation/results.json) | Consolidated scores, responses, reasoning, and evidence references |
| [`evaluation/test_cases.json`](evaluation/test_cases.json) | Consolidated prompts, expected safe behavior, and defenses |
| [`evaluation/breaking_test_cases.json`](evaluation/breaking_test_cases.json) | Stronger failure-seeking prompt for each security category |
| [`evaluation/breaking_results.json`](evaluation/breaking_results.json) | Separate ledger for running and scoring the breaking suite |
| [`evidence/aria-runtime-log-2026-09-19.md`](evidence/aria-runtime-log-2026-09-19.md) | Sanitized terminal evidence |
| [`evidence/session-log.md`](evidence/session-log.md) | Compact evidence register |

## Final submission steps

1. Upload `docs/week6-submission-report.docx` to Google Drive and open it as a Google Doc.
2. Confirm the three screenshots render correctly and set the required sharing access.
3. Submit the Google Doc link through the [Week 6 form](https://forms.gle/5cHmQJGxdC3X3Lrh8).

## Source

- Upstream exercise: <https://github.com/The-Gen-Academy/week6_neobank_aria_agent>
- Selected path: **Path A — ARIA hosted locally**
- Deadline in the supplied handout: **September 20, 2026 at 11:59 PM PT**
