# Week 4 step 3af: reviewed LangSmith baseline

## User prompt

> Let's move to the next step.

## Established next step and bounded interpretation

Checkpoint `4a414b6` freezes thirty explicitly approved expected behaviors and
records the local 29/30 fake-provider baseline. The documented next step is to
upload that same reviewed cohort to LangSmith, run one fake-only experiment, and
record actual dataset, experiment, and trace links.

- Preserve the reviewed/source digests, case recipes, expected outcomes, original
  eleven-case defaults, and previously saved artifacts.
- Add a separate opt-in uploader with immutable dataset readback, bounded calls,
  typed errors, deterministic evaluators, and count-only trace payloads.
- Run no OpenAI, Nebius, You.com, Tavily, Mem0, or LLM-judge calls. Only LangSmith
  dataset/experiment operations are external. Do not change environment files.
- Prove offline behavior and redaction before the authorized uploaded run.
- Record the actual failure, runtime overrun, and missing trace evidence if any;
  approval of expectations is not an implementation pass.
- Stop before production repair, another milestone, a commit, or a push.

## Concept

A reviewed dataset fixes the expected answers. An experiment measures a particular
implementation against those answers. Uploading an experiment makes its measured
outcomes and executed paths inspectable; it does not change a failed answer into
a correct one. Dataset readback prevents accidentally evaluating a different set.
