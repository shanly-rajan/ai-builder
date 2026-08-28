# ScholarPath M1 source-package flattening adjustment

> the additional scholarpath directory in src is not needed, adjust the files
> accordingly and stage the files to commit

Implementation interpretation:

- Move the physical package contents from `src/scholarpath/` directly into `src/`.
- Preserve the public `scholarpath` Python import namespace through packaging metadata.
- Update affected tests and documentation.
- Run all quality gates.
- Stage the resulting changes without creating a commit.
