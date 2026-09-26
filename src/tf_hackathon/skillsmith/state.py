"""Skillsmith's local memory: processed sessions and open skill proposals."""

import json
from datetime import UTC, datetime
from pathlib import Path


class State:
    def __init__(self, path: Path):
        self.path = path
        self._data = json.loads(path.read_text()) if path.exists() else {}
        self._data.setdefault("processed", {})
        self._data.setdefault("proposals", {})

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2))

    def is_processed(self, session_id: str) -> bool:
        return session_id in self._data["processed"]

    def mark_processed(self, session_ids: list[str], note: str) -> None:
        now = datetime.now(UTC).isoformat()
        for sid in session_ids:
            self._data["processed"][sid] = {"at": now, "note": note}
        self._save()

    def record_proposal(self, pr_number: int, proposal: dict) -> None:
        self._data["proposals"][str(pr_number)] = proposal
        self._save()

    def proposal(self, pr_number: int) -> dict | None:
        return self._data["proposals"].get(str(pr_number))

    def close_proposal(self, pr_number: int, outcome: str) -> None:
        if p := self._data["proposals"].get(str(pr_number)):
            p["outcome"] = outcome
            self._save()
