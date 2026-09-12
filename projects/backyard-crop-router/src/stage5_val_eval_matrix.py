"""Evaluate the tuned crop router and save an annotated confusion matrix."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import classification_report, confusion_matrix

from stage2_baseline_eval import LABELS, load_validation_split
from stage4_merge_smoke_test import (
    DEFAULT_ADAPTER_PATH,
    DEFAULT_MODEL_ID,
    classify,
    load_merged_model,
)

plt.switch_backend("Agg")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "farming_tickets.csv"
DEFAULT_MATRIX_PATH = PROJECT_ROOT / "artifacts" / "confusion_matrix.png"
DISPLAY_LABELS = [
    "Nutrient",
    "Pest",
    "Watering",
    "Fungal/Disease",
]


def parse_args() -> argparse.Namespace:
    """Parse validation, model, adapter, output, and device options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--adapter-path", type=Path, default=DEFAULT_ADAPTER_PATH)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--matrix-path", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--device",
        choices=("auto", "cuda", "mps", "cpu"),
        default="auto",
        help="Inference device; auto prefers CUDA, then Apple MPS, then CPU.",
    )
    return parser.parse_args()


def save_confusion_matrix(truth: list[str], predictions: list[str], path: Path) -> None:
    """Render and save a labeled confusion matrix as a PNG image."""
    matrix = confusion_matrix(truth, predictions, labels=LABELS)
    path.parent.mkdir(parents=True, exist_ok=True)

    sns.set_theme(style="whitegrid")
    figure, axis = plt.subplots(figsize=(9, 7))
    sns.heatmap(
        matrix,
        annot=True,
        fmt="d",
        cmap="YlGn",
        cbar=False,
        square=True,
        linewidths=0.5,
        xticklabels=DISPLAY_LABELS,
        yticklabels=DISPLAY_LABELS,
        ax=axis,
    )
    axis.set_title("Fine-Tuned Crop Router — Validation Confusion Matrix")
    axis.set_xlabel("Predicted category")
    axis.set_ylabel("True category")
    axis.tick_params(axis="x", rotation=25)
    axis.tick_params(axis="y", rotation=0)
    figure.tight_layout()
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    """Classify every validation ticket, report metrics, and save the matrix."""
    args = parse_args()
    validation = load_validation_split(args.data, args.seed)
    load_merged_model(args.model_id, args.adapter_path, args.device)

    predictions: list[str] = []
    observations = validation["text"].tolist()
    for index, observation in enumerate(observations, start=1):
        predictions.append(classify(observation))
        print(f"Evaluated {index}/{len(observations)} validation tickets")

    truth = validation["category_truth"].tolist()
    print("\nFine-tuned validation classification report")
    print(
        classification_report(
            truth,
            predictions,
            labels=LABELS,
            target_names=LABELS,
            digits=4,
            zero_division=0,
        )
    )

    save_confusion_matrix(truth, predictions, args.matrix_path)
    print(f"Confusion matrix saved to {args.matrix_path}")


if __name__ == "__main__":
    main()
