"""Replay a private excerpt-subject diagnostic offline without printing its contents."""

import argparse
from pathlib import Path
from typing import NoReturn

from scholarpath.evaluation.grounding_replay import (
    PrivateReplayError,
    read_private_replay,
    replay_snapshot,
)


class _PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        """Suppress argparse's normal echo of unrecognized private arguments."""
        raise PrivateReplayError("Private replay arguments are invalid")


def main(argv: list[str] | None = None) -> int:
    """Report only counts; a matching failure is not a successful verification."""
    parser = _PrivateArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Private grounding replay JSON file")
    try:
        args = parser.parse_args(argv)
        snapshot = read_private_replay(args.path)
        summary = replay_snapshot(snapshot)
    except (PrivateReplayError, ValueError, OSError):
        print("Private grounding replay could not be read or validated. No content displayed.")
        return 2
    print(summary.model_dump_json())
    print("Excerpt checks only: this does not establish full verification or Research Fit.")
    return 0 if summary.changed_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
