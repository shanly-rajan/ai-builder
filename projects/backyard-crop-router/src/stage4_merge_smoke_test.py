"""Merge the trained LoRA adapter and run assertion-backed smoke tests."""

from __future__ import annotations

import argparse
from pathlib import Path

import torch
from peft import PeftModel
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    PreTrainedModel,
    PreTrainedTokenizerBase,
)

from stage3_train_lora import LABELS, SYSTEM_PROMPT


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ADAPTER_PATH = PROJECT_ROOT / "artifacts" / "adapter_weights"
DEFAULT_MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"

SMOKE_TESTS = [
    (
        "The older leaves on my chilli plant are pale between green veins, but "
        "the potting mix has normal moisture.",
        "Nutrient Adjustment Needed",
    ),
    (
        "Sticky curled bean shoots are covered in tiny green insects, with ants "
        "crawling around them.",
        "Pest Control Required",
    ),
    (
        "My lettuce droops every afternoon and the soil is bone dry below the "
        "surface because its drip line is blocked.",
        "Irrigation/Watering Issue",
    ),
    (
        "A dusty white coating keeps returning on the squash leaves and is "
        "spreading to nearby foliage.",
        "Fungal/Disease Treatment",
    ),
    (
        "After a week of damp weather, brown spots with yellow rings are "
        "expanding across the tomato leaves.",
        "Fungal/Disease Treatment",
    ),
]

_MODEL: PreTrainedModel | None = None
_TOKENIZER: PreTrainedTokenizerBase | None = None
_DEVICE: torch.device | None = None


def parse_args() -> argparse.Namespace:
    """Parse model, adapter, and device options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter-path", type=Path, default=DEFAULT_ADAPTER_PATH)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument(
        "--device",
        choices=("auto", "cuda", "mps", "cpu"),
        default="auto",
        help="Inference device; auto prefers CUDA, then Apple MPS, then CPU.",
    )
    return parser.parse_args()


def resolve_device(requested: str) -> torch.device:
    """Resolve an explicit device or select the best available accelerator."""
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


def load_merged_model(
    model_id: str = DEFAULT_MODEL_ID,
    adapter_path: Path = DEFAULT_ADAPTER_PATH,
    requested_device: str = "auto",
) -> None:
    """Load the base model, apply the LoRA adapter, and merge its weights."""
    global _DEVICE, _MODEL, _TOKENIZER  # pylint: disable=global-statement

    if not adapter_path.joinpath("adapter_config.json").is_file():
        raise FileNotFoundError(
            f"LoRA adapter not found at {adapter_path}. Run Stage 3 first."
        )

    device = resolve_device(requested_device)
    dtype = torch.float32 if device.type == "cpu" else torch.float16
    tokenizer = AutoTokenizer.from_pretrained(adapter_path)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(
        model_id,
        dtype=dtype,
        low_cpu_mem_usage=True,
    ).to(device)
    adapter_model = PeftModel.from_pretrained(base_model, adapter_path)
    merged_model = adapter_model.merge_and_unload()
    merged_model.eval()
    merged_model.requires_grad_(False)

    _DEVICE = device
    _MODEL = merged_model
    _TOKENIZER = tokenizer
    print(f"Merged adapter from {adapter_path} into {model_id} on {device}")


def classify(observation: str) -> str:
    """Classify one crop observation using the merged model weights."""
    if _MODEL is None or _TOKENIZER is None or _DEVICE is None:
        raise RuntimeError("Model is not loaded. Call load_merged_model() first.")
    if not observation.strip():
        raise ValueError("Observation must not be empty")

    prompt = _TOKENIZER.apply_chat_template(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Observation: {observation.strip()}"},
        ],
        tokenize=False,
        add_generation_prompt=True,
    )
    model_inputs = _TOKENIZER(prompt, return_tensors="pt").to(_DEVICE)

    with torch.inference_mode():
        generated_ids = _MODEL.generate(
            **model_inputs,
            max_new_tokens=16,
            do_sample=False,
            pad_token_id=_TOKENIZER.eos_token_id,
        )

    completion_ids = generated_ids[0, model_inputs["input_ids"].shape[-1] :]
    raw_output = _TOKENIZER.decode(completion_ids, skip_special_tokens=True)
    normalized_output = " ".join(raw_output.strip().split())

    exact_match = next(
        (label for label in LABELS if normalized_output.casefold() == label.casefold()),
        None,
    )
    if exact_match is not None:
        return exact_match

    contained_matches = [
        label for label in LABELS if label.casefold() in normalized_output.casefold()
    ]
    if len(contained_matches) == 1:
        return contained_matches[0]

    raise RuntimeError(f"Model returned an unknown category: {raw_output!r}")


def run_smoke_tests() -> None:
    """Assert correct routing for five unseen observations across all classes."""
    failures: list[str] = []
    for index, (observation, expected) in enumerate(SMOKE_TESTS, start=1):
        try:
            predicted = classify(observation)
        except (RuntimeError, ValueError) as error:
            failures.append(f"Ticket {index}: inference error: {error}")
            print(f"FAIL {index}/5 | expected={expected} | error={error}")
            continue

        passed = predicted == expected
        print(
            f"{'PASS' if passed else 'FAIL'} {index}/5 | "
            f"expected={expected} | predicted={predicted}"
        )
        if not passed:
            failures.append(
                f"Ticket {index}: expected {expected!r}, predicted {predicted!r}"
            )

    if failures:
        details = "\n".join(f"- {failure}" for failure in failures)
        raise AssertionError(f"Smoke test failed:\n{details}")

    print("Smoke test passed: 5/5 tickets classified correctly.")


def main() -> None:
    """Merge the trained adapter and execute all smoke-test assertions."""
    args = parse_args()
    load_merged_model(args.model_id, args.adapter_path, args.device)
    run_smoke_tests()


if __name__ == "__main__":
    main()
