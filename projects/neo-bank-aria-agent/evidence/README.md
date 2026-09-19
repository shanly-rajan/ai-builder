# Evidence folder

Save screenshots here using the case ID, for example `JB-01.png` or
`PII-01.png`. Image files are ignored by Git by default so evidence can be
reviewed before deliberately adding it to a submission.

The canonical evidence references are recorded in `evaluation/results.json`; the older
`evaluation/breaking_results.json` is retained as an audit copy.

Before submitting, confirm every screenshot:

- shows the prompt and relevant ARIA response;
- excludes the OpenAI API key and unrelated desktop content;
- contains only the fictional workshop data;
- matches the path recorded in `evaluation/results.json`.

The consolidated breaking-suite screenshots use the IDs `JB-02`, `OBF-02`, `SDE-02`, `PI-02`,
`RT-02`, `CRE-02`, `PII-02`, and `SOC-02`.
