"""Structured JSONL event log -- the observability layer.

One line per event: timestamp, node, and whatever context the caller passes.
Kept as plain local files on purpose (no third-party tracing service sees
source code)."""

import json
import time

from .config import CONFIG


def log_event(node: str, **fields) -> None:
    CONFIG.workdir_root.mkdir(parents=True, exist_ok=True)
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "node": node, **fields}
    with CONFIG.log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
