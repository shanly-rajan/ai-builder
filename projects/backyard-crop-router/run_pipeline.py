"""Run crop-router stages 1 through 5 in order using the active environment."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"


def parse_args() -> argparse.Namespace:
    """Parse shared model and accelerator options for the pipeline."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument(
        "--device",
        choices=("auto", "cuda", "mps", "cpu"),
        default="auto",
        help="Inference device for Stages 2, 4, and 5.",
    )
    return parser.parse_args()


def ensure_project_environment() -> None:
    """Fail fast when the runner is not using this project's virtual environment."""
    expected_environment = (PROJECT_ROOT / ".venv").resolve()
    active_environment = Path(sys.prefix).resolve()
    if active_environment != expected_environment:
        raise RuntimeError(
            "Activate projects/backyard-crop-router/.venv before running the "
            "pipeline."
        )


def run_stage(stage_number: int, description: str, command: list[str]) -> None:
    """Execute one pipeline stage and stop immediately if it fails."""
    print(f"\n{'=' * 72}\nStage {stage_number}: {description}\n{'=' * 72}", flush=True)
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def main() -> None:
    """Execute dataset generation, baseline, training, smoke test, and evaluation."""
    args = parse_args()
    ensure_project_environment()
    python = sys.executable

    stages = [
        (1, "Generate balanced dataset", [python, str(SRC_DIR / "stage1_dataset.py")]),
        (
            2,
            "Evaluate zero-shot baseline",
            [
                python,
                str(SRC_DIR / "stage2_baseline_eval.py"),
                "--model-id",
                args.model_id,
                "--device",
                args.device,
            ],
        ),
        (
            3,
            "Train LoRA adapter",
            [
                python,
                str(SRC_DIR / "stage3_train_lora.py"),
                "--model-id",
                args.model_id,
            ],
        ),
        (
            4,
            "Merge adapter and run smoke test",
            [
                python,
                str(SRC_DIR / "stage4_merge_smoke_test.py"),
                "--model-id",
                args.model_id,
                "--device",
                args.device,
            ],
        ),
        (
            5,
            "Evaluate tuned model and save confusion matrix",
            [
                python,
                str(SRC_DIR / "stage5_val_eval_matrix.py"),
                "--model-id",
                args.model_id,
                "--device",
                args.device,
            ],
        ),
    ]

    for stage_number, description, command in stages:
        run_stage(stage_number, description, command)

    print("\nPipeline completed successfully: Stages 1 through 5 passed.")


if __name__ == "__main__":
    main()
