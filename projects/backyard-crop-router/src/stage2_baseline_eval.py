"""Evaluate the frozen Qwen base model as a zero-shot crop-ticket router."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import pandas as pd
import torch
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from transformers import AutoModelForCausalLM, AutoTokenizer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "farming_tickets.csv"
DEFAULT_MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"

LETTER_TO_LABEL = {
    "A": "Nutrient Adjustment Needed",
    "B": "Pest Control Required",
    "C": "Irrigation/Watering Issue",
    "D": "Fungal/Disease Treatment",
}
LABELS = list(LETTER_TO_LABEL.values())

SYSTEM_PROMPT = (
    "You are a backyard farming triage router. Select the single best category "
    "for the observation. Respond with exactly one letter: A, B, C, or D."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--device",
        choices=("auto", "cuda", "mps", "cpu"),
        default="auto",
        help="Inference device; auto prefers CUDA, then Apple MPS, then CPU.",
    )
    return parser.parse_args()


def resolve_device(requested: str) -> torch.device:
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available")
    if requested == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("MPS was requested but is not available")
    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def load_validation_split(data_path: Path, seed: int) -> pd.DataFrame:
    dataframe = pd.read_csv(data_path)
    required_columns = {"text", "category_truth"}
    missing_columns = required_columns.difference(dataframe.columns)
    if missing_columns:
        raise ValueError(f"Dataset is missing columns: {sorted(missing_columns)}")

    unknown_labels = set(dataframe["category_truth"]).difference(LABELS)
    if unknown_labels:
        raise ValueError(f"Dataset contains unknown labels: {sorted(unknown_labels)}")

    _, validation = train_test_split(
        dataframe,
        test_size=0.20,
        random_state=seed,
        stratify=dataframe["category_truth"],
    )
    return validation.reset_index(drop=True)


def format_prompt(tokenizer: AutoTokenizer, observation: str) -> str:
    choices = "\n".join(
        f"{letter}. {label}" for letter, label in LETTER_TO_LABEL.items()
    )
    user_prompt = (
        f"Classify this backyard farming observation.\n\n{choices}\n\n"
        f"Observation: {observation}\n\nAnswer:"
    )
    return tokenizer.apply_chat_template(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        tokenize=False,
        add_generation_prompt=True,
    )


def get_candidate_token_ids(tokenizer: AutoTokenizer) -> list[int]:
    token_ids: list[int] = []
    for letter in LETTER_TO_LABEL:
        encoded = tokenizer.encode(letter, add_special_tokens=False)
        if len(encoded) != 1:
            raise RuntimeError(
                f"Expected '{letter}' to map to one token, but received {encoded}"
            )
        token_ids.append(encoded[0])
    return token_ids


def predict_labels(
    model: AutoModelForCausalLM,
    tokenizer: AutoTokenizer,
    observations: Sequence[str],
    device: torch.device,
    batch_size: int,
) -> list[str]:
    """Choose only among A/B/C/D using the next-token logits."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    candidate_token_ids = get_candidate_token_ids(tokenizer)
    candidate_letters = list(LETTER_TO_LABEL)
    predictions: list[str] = []

    for start in range(0, len(observations), batch_size):
        batch = observations[start : start + batch_size]
        prompts = [format_prompt(tokenizer, text) for text in batch]
        model_inputs = tokenizer(
            prompts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=1024,
        ).to(device)

        with torch.inference_mode():
            next_token_logits = model(**model_inputs).logits[:, -1, :]

        choice_logits = next_token_logits[:, candidate_token_ids]
        choice_indices = choice_logits.argmax(dim=-1).cpu().tolist()
        predictions.extend(
            LETTER_TO_LABEL[candidate_letters[index]] for index in choice_indices
        )

        completed = min(start + len(batch), len(observations))
        print(f"Evaluated {completed}/{len(observations)} validation tickets")

    return predictions


def main() -> None:
    args = parse_args()
    device = resolve_device(args.device)
    validation = load_validation_split(args.data, args.seed)

    print(f"Loading frozen baseline model: {args.model_id}")
    print(f"Device: {device}; validation tickets: {len(validation)}")

    tokenizer = AutoTokenizer.from_pretrained(args.model_id)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    dtype = torch.float32 if device.type == "cpu" else torch.float16
    model = AutoModelForCausalLM.from_pretrained(
        args.model_id,
        dtype=dtype,
        low_cpu_mem_usage=True,
    ).to(device)
    model.eval()
    model.requires_grad_(False)

    predictions = predict_labels(
        model=model,
        tokenizer=tokenizer,
        observations=validation["text"].tolist(),
        device=device,
        batch_size=args.batch_size,
    )

    print("\nZero-shot baseline classification report")
    print(
        classification_report(
            validation["category_truth"],
            predictions,
            labels=LABELS,
            target_names=LABELS,
            digits=4,
            zero_division=0,
        )
    )


if __name__ == "__main__":
    main()
