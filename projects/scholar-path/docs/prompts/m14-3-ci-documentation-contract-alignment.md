# ScholarPath Milestone M14.3: CI documentation-contract alignment

Fix the failing ScholarPath GitHub Actions quality job as a bounded repository repair.

Inspect the workflow and reproduce its commands locally before changing code. Preserve the
current runtime behaviour and quality gates. Determine whether the failure is caused by active
implementation defects or by stale repository contracts.

The submission write-up and five-minute demonstration document were deliberately retired in
earlier commits because they were outdated. Do not restore those obsolete documents merely to
satisfy stale tests. Instead:

- remove active README links to the retired documents;
- update documentation contracts so they verify the current reviewer entry points and retained
  milestone history;
- keep useful link-integrity and artifact-presence checks for active documentation;
- preserve historical build-journal entries and archived prompts;
- do not weaken linting, type checking, coverage, runtime tests, terminology checks, or CI.

Run the exact non-live GitHub Actions quality commands after the repair. Save this prompt, update
the build journal, and commit the bounded repair separately.
