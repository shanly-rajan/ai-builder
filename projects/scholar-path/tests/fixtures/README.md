# Test fixtures

M1 provides deterministic factory functions in `factories.py` for one synthetic
Candidate, eight Prospective Supervisors, six Verified Supervisors, and five Research
Fit assessments.

```text
1 Candidate
    └── 8 Prospective Supervisors
          └── 6 Verified Supervisors
                └── 5 Research Fit assessments
```

The records use invented names and institutions, fixed timezone-aware timestamps, and
reserved `scholarpath.example` URLs. They contain no secrets, randomness, live page
content, external calls, or generated model output. New fixtures must preserve those
properties and remain usable without network access.
