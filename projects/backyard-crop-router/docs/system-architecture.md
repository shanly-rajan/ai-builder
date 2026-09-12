# System Architecture

The Backyard Crop Router fine-tunes a small language model to route a farming
observation to one of four specialist action categories. The project contains
an offline training pipeline and a reusable local inference function; it does
not yet expose a production API.

## Training and evaluation flow

```mermaid
flowchart LR
    A[Stage 1<br/>Generate 160 tickets] --> B[Seed-42 stratified split]
    B -->|32 validation| C[Stage 2<br/>Frozen Qwen baseline]
    B -->|128 training| D[Stage 3<br/>Chat formatting]
    D --> E[TRL SFTTrainer<br/>PEFT LoRA]
    E --> F[(Local adapter weights)]
    F --> G[Stage 4<br/>merge_and_unload]
    G --> H[5-ticket smoke test]
    G --> I[Stage 5<br/>32-ticket evaluation]
    C --> J[Baseline metrics]
    I --> K[Fine-tuned metrics]
    J --> L[Delta analysis]
    K --> L
    I --> M[Confusion matrix PNG]
```

## Runtime classification flow

```mermaid
sequenceDiagram
    actor Caller
    participant Router as classify()
    participant Tokenizer
    participant Model as Merged Qwen + LoRA

    Caller->>Router: Farming observation
    Router->>Tokenizer: System persona + observation
    Tokenizer->>Model: Token IDs
    Model-->>Router: Generated category
    Router->>Router: Normalize and validate taxonomy
    alt One known category
        Router-->>Caller: Category name
    else Unknown or ambiguous output
        Router-->>Caller: Explicit RuntimeError
    end
```

## Key design decisions

| Decision | Reason | Trade-off |
|---|---|---|
| Qwen 1.5B | Small enough for fast local routing | Less general capability than a larger model |
| LoRA on attention projections | Trains only 0.141% of parameters | Adapter quality depends heavily on dataset coverage |
| Completion-only chat loss | Optimizes the target category response | Requires consistent prompt formatting |
| Adapter merge | Simple standalone inference path | Merged base weights still consume model-sized memory |
| Fixed four-category validation | Predictable downstream contract | New categories require data and retraining |

## Architecture boundaries

- **Included:** dataset generation, baseline evaluation, LoRA training, local
  inference, smoke tests, metrics, and confusion-matrix evidence.
- **Not included:** HTTP serving, authentication, model registry, production
  monitoring, human escalation, and continuous retraining.
- **Primary quality risk:** the synthetic random split shares symptom-template
  families between training and validation. Independent and ambiguous examples
  are required before production use.

