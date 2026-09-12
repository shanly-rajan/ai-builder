# Backyard Crop Router

A small, fast farming-support router created by fine-tuning
`Qwen/Qwen2.5-1.5B-Instruct` with LoRA. It assigns each backyard crop
observation to one of four action categories:

- Nutrient Adjustment Needed
- Pest Control Required
- Irrigation/Watering Issue
- Fungal/Disease Treatment

## Results at a glance

- All five implementation stages pass end to end on Apple Silicon MPS.
- Zero-shot baseline is measured at **65.62% accuracy** and **0.5814 macro F1**.
- LoRA training completed with a final loss of **0.013273**.
- The merged model passed all **5/5** smoke-test assertions.
- Fine-tuned validation reached **100% accuracy** and **1.0000 macro F1**.

## Pipeline at a glance

```mermaid
flowchart LR
    A[Generate tickets] --> B[Measure zero-shot baseline]
    B --> C[Train LoRA adapter]
    C --> D[Merge and smoke-test]
    D --> E[Evaluate and compare]
```

| Stage | Status | What it does |
|---|---|---|
| 0. Setup | Complete | Creates an isolated Python environment and installs the ML dependencies. |
| 1. Dataset | Complete | Generates 160 unique synthetic farming tickets, balanced at 40 per category. |
| 2. Baseline | Complete | Tests the frozen base model on a stratified 32-ticket validation split. |
| 3. LoRA training | Complete | Formats training examples as chats and trains a lightweight adapter. |
| 4. Merge and smoke test | Complete | Merges the adapter into Qwen and verifies five representative tickets. |
| 5. Final evaluation | Complete | Compares tuned results with the baseline and creates a confusion matrix. |

## Setup

Python 3.12 is recommended for compatibility with the ML packages. This
workstation uses pyenv, so the setup command selects its installed Python
3.12.13 explicitly.

```bash
cd projects/backyard-crop-router
PYENV_VERSION=3.12.13 python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

In VS Code, select `projects/backyard-crop-router/.venv/bin/python` with
**Python: Select Interpreter**. This lets Pylance and Pylint resolve the
project's isolated dependencies.

## Stage 1: generate the dataset

```bash
python src/stage1_dataset.py
```

Output: `data/farming_tickets.csv` with the columns `text` and
`category_truth`.

## Stage 2: run the zero-shot baseline

```bash
python src/stage2_baseline_eval.py
```

The script uses a fixed seed and an 80/20 stratified split. Instead of parsing
free-form model text, it selects directly among the next-token logits for A,
B, C, and D.

### Measured baseline

| Category | Precision | Recall | F1 |
|---|---:|---:|---:|
| Nutrient Adjustment | 1.0000 | 0.6250 | 0.7692 |
| Pest Control | 0.4444 | 1.0000 | 0.6154 |
| Irrigation/Watering | 0.8889 | 1.0000 | 0.9412 |
| Fungal/Disease | 0.0000 | 0.0000 | 0.0000 |
| **Macro average** | **0.5833** | **0.6562** | **0.5814** |

Overall baseline accuracy is **65.62% (21/32)**. The base model completely
missed fungal/disease tickets, which gives the LoRA stage a clear improvement
target.

## Stage 3: train the LoRA adapter

```bash
python src/stage3_train_lora.py
```

The training split contains 128 examples, balanced at 32 per category. Prompts
are formatted as system, observation, and target-category chat turns. Training
uses completion-only loss so only the assistant's answer contributes to the
objective. The effective batch size produces 16 optimizer steps per epoch and
48 steps across the full run.

| Setting | Value |
|---|---|
| LoRA rank / alpha / dropout | `8` / `16` / `0.05` |
| Target modules | `q_proj`, `k_proj`, `v_proj`, `o_proj` |
| Batch size / accumulation | `4` / `2` (effective batch `8`) |
| Learning rate / epochs | `2e-4` / `3` |
| Precision | FP16 |
| Trainable parameters | 2,179,072 (0.1410%) |

Adapter weights are written to `artifacts/adapter_weights/`, which is excluded
from Git. Training completed in 48 optimizer steps with a final loss of
`0.013273`. To validate the trainer setup without changing weights, run:

```bash
python src/stage3_train_lora.py --dry-run
```

## Stage 4: merge and smoke-test

```bash
python src/stage4_merge_smoke_test.py
```

The script loads the base model and adapter, calls `merge_and_unload()`, and
exposes `classify(observation: str) -> str`. It raises an `AssertionError` if
any smoke-test prediction is incorrect.

```text
PASS 1/5 | Nutrient Adjustment Needed
PASS 2/5 | Pest Control Required
PASS 3/5 | Irrigation/Watering Issue
PASS 4/5 | Fungal/Disease Treatment
PASS 5/5 | Fungal/Disease Treatment
Smoke test passed: 5/5 tickets classified correctly.
```

## Stage 5: evaluate and compare

```bash
python src/stage5_val_eval_matrix.py
```

All 32 held-out tickets were classified correctly after fine-tuning.

| Metric | Baseline | Fine-tuned | Delta |
|---|---:|---:|---:|
| Accuracy | 0.6562 | 1.0000 | +0.3438 |
| Macro precision | 0.5833 | 1.0000 | +0.4167 |
| Macro recall | 0.6562 | 1.0000 | +0.3438 |
| Macro F1 | 0.5814 | 1.0000 | +0.4186 |

### Recall analysis

| Category | Baseline recall | Fine-tuned recall | Delta |
|---|---:|---:|---:|
| Nutrient Adjustment | 0.6250 | 1.0000 | +0.3750 |
| Pest Control | 1.0000 | 1.0000 | 0.0000 |
| Irrigation/Watering | 1.0000 | 1.0000 | 0.0000 |
| Fungal/Disease | 0.0000 | 1.0000 | +1.0000 |

The baseline recall was highly asymmetric: it found every pest and watering
ticket but missed every fungal/disease ticket. LoRA removed that blind spot and
also recovered the three missed nutrient tickets.

![Fine-tuned validation confusion matrix](artifacts/confusion_matrix.png)

The perfect score is an in-distribution result. The synthetic dataset reuses
symptom-template families across crops, so the random split is easier than
production traffic. A production gate should add independently authored cases,
ambiguous multi-symptom tickets, and a split grouped by symptom template.

## Run the full pipeline

With the project environment activated, this command executes Stages 1–5 in
order and stops on the first failure:

```bash
python run_pipeline.py
```

The full run regenerates the dataset and retrains the adapter before evaluation.

## Submission assets

- [System architecture](docs/system-architecture.md)
- [Submission summary](docs/submission-summary.md)

GitHub submission link:
[github.com/shanly-rajan/ai-builder/tree/main/projects/backyard-crop-router](https://github.com/shanly-rajan/ai-builder/tree/main/projects/backyard-crop-router)

## Generated outputs

| Output | Git policy | Purpose |
|---|---|---|
| `data/farming_tickets.csv` | Tracked | Reproducible 160-ticket dataset |
| `artifacts/confusion_matrix.png` | Tracked | Final validation evidence |
| `artifacts/adapter_weights/` | Ignored | Local generated model weights |

The base model is downloaded from Hugging Face on first use. Neither the model
cache nor generated adapter weights are committed to this repository.
