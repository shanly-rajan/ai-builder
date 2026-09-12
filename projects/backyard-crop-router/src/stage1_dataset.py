"""Generate a balanced synthetic dataset of backyard-crop support tickets."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "farming_tickets.csv"

LABEL_TEMPLATES: dict[str, dict[str, list[str]]] = {
    "Nutrient Adjustment Needed": {
        "crops": [
            "tomato",
            "pepper",
            "cucumber",
            "zucchini",
            "kale",
            "spinach",
            "lettuce",
            "bean",
            "strawberry",
            "eggplant",
        ],
        "symptoms": [
            (
                "My {crop} plants have uniformly pale older leaves, starting at "
                "the tips, and new growth is much slower than normal."
            ),
            (
                "The oldest leaves on my {crop} show yellow tissue between green "
                "veins even though the soil is evenly moist."
            ),
            (
                "My {crop} is stunted and the lower leaves are developing a dull "
                "purple tint; I have not fertilized this bed this season."
            ),
            (
                "Leaf edges on my {crop} are yellowing and turning brown while the "
                "centers stay green, and the stems seem weak."
            ),
        ],
    },
    "Pest Control Required": {
        "crops": [
            "tomato",
            "pepper",
            "cucumber",
            "squash",
            "kale",
            "broccoli",
            "lettuce",
            "bean",
            "strawberry",
            "basil",
        ],
        "symptoms": [
            (
                "New leaves on my {crop} are curled and sticky, with clusters of "
                "tiny green insects underneath and ants moving between them."
            ),
            (
                "My {crop} leaves have fine pale stippling and delicate webbing on "
                "their undersides; tiny moving specks are visible up close."
            ),
            (
                "Something is chewing irregular holes through my {crop} leaves, "
                "and I found dark droppings plus a small caterpillar nearby."
            ),
            (
                "Several {crop} leaves contain winding white tunnels, and a tiny "
                "larva can be seen inside one of the trails."
            ),
        ],
    },
    "Irrigation/Watering Issue": {
        "crops": [
            "tomato",
            "pepper",
            "cucumber",
            "zucchini",
            "kale",
            "spinach",
            "lettuce",
            "bean",
            "strawberry",
            "herb planter",
        ],
        "symptoms": [
            (
                "My {crop} wilts by mid-morning and the soil is dry several "
                "centimetres down; the container feels unusually light."
            ),
            (
                "The {crop} has limp yellow lower leaves while its soil remains "
                "soggy for days and the pot drains very slowly."
            ),
            (
                "Leaves on my {crop} are crisping at the edges after several hot "
                "days, and the drip emitter beside it appears blocked."
            ),
            (
                "My {crop} alternates between drooping and recovering because the "
                "raised bed dries out completely between irregular waterings."
            ),
        ],
    },
    "Fungal/Disease Treatment": {
        "crops": [
            "tomato",
            "pepper",
            "cucumber",
            "zucchini",
            "kale",
            "spinach",
            "lettuce",
            "bean",
            "strawberry",
            "basil",
        ],
        "symptoms": [
            (
                "A white powdery coating is spreading across my {crop} leaves; it "
                "returns after wiping and nearby leaves are starting to curl."
            ),
            (
                "My {crop} has expanding brown leaf spots with yellow halos, and "
                "the damaged leaves are dropping after recent humid weather."
            ),
            (
                "The base of my {crop} stem is dark and soft, roots look brown, and "
                "the plant is collapsing even though the soil is wet."
            ),
            (
                "Water-soaked patches on my {crop} are turning dark and spreading "
                "quickly from lower leaves after several cool rainy nights."
            ),
        ],
    },
}


def build_rows() -> list[dict[str, str]]:
    """Build 40 unique observations for each routing category."""
    rows: list[dict[str, str]] = []
    for label, components in LABEL_TEMPLATES.items():
        for crop in components["crops"]:
            for symptom in components["symptoms"]:
                rows.append(
                    {
                        "text": symptom.format(crop=crop),
                        "category_truth": label,
                    }
                )

    counts = Counter(row["category_truth"] for row in rows)
    expected_counts = {label: 40 for label in LABEL_TEMPLATES}
    if counts != expected_counts:
        raise RuntimeError(f"Dataset is not balanced: {dict(counts)}")
    if len({row["text"] for row in rows}) != len(rows):
        raise RuntimeError("Dataset contains duplicate observations")

    return rows


def write_dataset(rows: list[dict[str, str]], output_path: Path = OUTPUT_PATH) -> None:
    """Write rows using the schema consumed by the later pipeline stages."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["text", "category_truth"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rows = build_rows()
    write_dataset(rows)

    counts = Counter(row["category_truth"] for row in rows)
    print(f"Wrote {len(rows)} observations to {OUTPUT_PATH}")
    for label in LABEL_TEMPLATES:
        print(f"  {label}: {counts[label]}")


if __name__ == "__main__":
    main()
