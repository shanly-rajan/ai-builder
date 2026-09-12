"""Fine-tune Qwen as a crop-ticket router with a lightweight LoRA adapter."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import torch
from datasets import Dataset
from peft import LoraConfig, TaskType
from sklearn.model_selection import train_test_split
from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed
from trl import SFTConfig, SFTTrainer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "farming_tickets.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "adapter_weights"
DEFAULT_MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"

LABELS = [
    "Nutrient Adjustment Needed",
    "Pest Control Required",
    "Irrigation/Watering Issue",
    "Fungal/Disease Treatment",
]
SYSTEM_PROMPT = (
    "You are a backyard farming triage router. Classify each observation into "
    "exactly one of these categories: Nutrient Adjustment Needed, Pest Control "
    "Required, Irrigation/Watering Issue, or Fungal/Disease Treatment. Return "
    "only the category name."
)


def parse_args() -> argparse.Namespace:
    """Parse training paths and reproducibility options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the dataset, model, adapter, and trainer without training.",
    )
    return parser.parse_args()


def load_training_split(data_path: Path, seed: int) -> pd.DataFrame:
    """Return the 80% training partition matching the Stage 2 split."""
    dataframe = pd.read_csv(data_path)
    required_columns = {"text", "category_truth"}
    missing_columns = required_columns.difference(dataframe.columns)
    if missing_columns:
        raise ValueError(f"Dataset is missing columns: {sorted(missing_columns)}")

    unknown_labels = set(dataframe["category_truth"]).difference(LABELS)
    if unknown_labels:
        raise ValueError(f"Dataset contains unknown labels: {sorted(unknown_labels)}")

    training, _ = train_test_split(
        dataframe,
        test_size=0.20,
        random_state=seed,
        stratify=dataframe["category_truth"],
    )
    return training.reset_index(drop=True)


def to_chat_example(example: dict[str, str]) -> dict[str, list[dict[str, str]]]:
    """Map one CSV row to conversational prompt and completion turns."""
    return {
        "prompt": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Observation: {example['text']}",
            },
        ],
        "completion": [
            {
                "role": "assistant",
                "content": example["category_truth"],
            }
        ],
    }


def build_chat_dataset(training_frame: pd.DataFrame) -> Dataset:
    """Convert the training dataframe into TRL's conversational dataset format."""
    examples = [
        to_chat_example(
            {
                "text": row.text,
                "category_truth": row.category_truth,
            }
        )
        for row in training_frame.itertuples(index=False)
    ]
    return Dataset.from_list(examples)


def build_lora_config() -> LoraConfig:
    """Create the required low-rank adapter configuration for Qwen attention."""
    return LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
        bias="none",
    )


def build_training_config(output_dir: Path, seed: int) -> SFTConfig:
    """Create the requested three-epoch supervised fine-tuning configuration."""
    return SFTConfig(
        output_dir=str(output_dir),
        per_device_train_batch_size=4,
        gradient_accumulation_steps=2,
        learning_rate=2e-4,
        num_train_epochs=3,
        fp16=True,
        optim="adamw_torch",
        max_length=512,
        completion_only_loss=True,
        gradient_checkpointing=True,
        save_strategy="no",
        logging_steps=1,
        report_to="none",
        seed=seed,
        data_seed=seed,
        dataloader_pin_memory=False,
    )


def build_trainer(args: argparse.Namespace, train_dataset: Dataset) -> SFTTrainer:
    """Load Qwen and assemble an SFT trainer with its LoRA adapter."""
    tokenizer = AutoTokenizer.from_pretrained(args.model_id)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.model_id,
        dtype=torch.float16,
        low_cpu_mem_usage=True,
    )
    model.config.use_cache = False

    return SFTTrainer(
        model=model,
        args=build_training_config(args.output_dir, args.seed),
        train_dataset=train_dataset,
        processing_class=tokenizer,
        peft_config=build_lora_config(),
    )


def main() -> None:
    """Prepare the training split, run SFT, and save adapter-only weights."""
    args = parse_args()
    set_seed(args.seed)

    training_frame = load_training_split(args.data, args.seed)
    train_dataset = build_chat_dataset(training_frame)
    print(f"Training examples: {len(train_dataset)}")
    print(training_frame["category_truth"].value_counts().sort_index().to_string())

    trainer = build_trainer(args, train_dataset)
    trainer.model.print_trainable_parameters()

    if args.dry_run:
        print("Dry run complete; training and adapter save were skipped.")
        return

    train_result = trainer.train()
    trainer.save_model(str(args.output_dir))
    trainer.processing_class.save_pretrained(args.output_dir)

    print(f"Adapter weights saved to {args.output_dir}")
    print(f"Training loss: {train_result.training_loss:.6f}")


if __name__ == "__main__":
    main()
