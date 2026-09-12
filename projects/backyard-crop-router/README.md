# Backyard Crop Router

A small, fast farming-support router being built by fine-tuning
`Qwen/Qwen2.5-1.5B-Instruct` with LoRA. It assigns each backyard crop
observation to one of four action categories:

- Nutrient Adjustment Needed
- Pest Control Required
- Irrigation/Watering Issue
- Fungal/Disease Treatment

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
| 3. LoRA training | Pending | Formats training examples as chats and trains a lightweight adapter. |
| 4. Merge and smoke test | Pending | Merges the adapter into Qwen and verifies five representative tickets. |
| 5. Final evaluation | Pending | Compares tuned results with the baseline and creates a confusion matrix. |

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

## Remaining stages

Stages 3–5 will add LoRA training, adapter merging, assertion-backed smoke
tests, final validation metrics, the baseline delta, and an annotated confusion
matrix. This README will be updated with the measured results as each stage is
completed.
