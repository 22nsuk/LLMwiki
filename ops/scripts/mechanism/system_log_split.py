#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.mechanism.finalize_run_log_runtime import slugify_heading
else:
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.mechanism.finalize_run_log_runtime import slugify_heading

DEFAULT_SYSTEM_LOG = "system/system-log.md"
DEFAULT_EVENTS = "system/events.jsonl"
DEFAULT_DECISION_LOG = "system/decision-log.md"
EVENT_HEADING_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
CHRONOLOGY_ENTRY_RE = re.compile(r"^## \[\d{4}-\d{2}-\d{2}", re.MULTILINE)


def _parse_system_log(text: str) -> tuple[str, list[str]]:
    match = CHRONOLOGY_ENTRY_RE.search(text)
    if match is None:
        return text.strip(), []
    preamble = text[: match.start()].rstrip()
    entries_text = text[match.start() :]
    entries = [chunk.strip() for chunk in re.split(r"\n---\n", entries_text) if chunk.strip()]
    return preamble, entries


def _compose_system_log(preamble: str, entries: list[str]) -> str:
    if not entries:
        return f"{preamble}\n" if preamble else ""
    body = "\n---\n\n".join(entries)
    if preamble:
        return f"{preamble}\n\n---\n\n{body}\n"
    return f"{body}\n"


def _entry_heading(entry: str) -> str:
    match = EVENT_HEADING_RE.search(entry)
    if match:
        return match.group(1).strip()
    return ""


def migrate_system_log(
    vault: Path,
    *,
    system_log: str = DEFAULT_SYSTEM_LOG,
    events_out: str = DEFAULT_EVENTS,
    decision_log: str = DEFAULT_DECISION_LOG,
    tail_entries: int = 0,
) -> dict[str, object]:
    log_path = vault / system_log
    if not log_path.is_file():
        return {
            "status": "missing",
            "migrated_count": 0,
            "remaining_count": 0,
            "events_path": events_out,
            "decision_log_path": decision_log,
        }

    text = log_path.read_text(encoding="utf-8")
    preamble, entries = _parse_system_log(text)
    if tail_entries <= 0 or tail_entries >= len(entries):
        migrate_entries = entries
        remaining_entries: list[str] = []
    else:
        migrate_entries = entries[-tail_entries:]
        remaining_entries = entries[:-tail_entries]

    events_path = vault / events_out
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as handle:
        for entry in migrate_entries:
            heading = _entry_heading(entry)
            payload = {
                "event_kind": "system_log_migration",
                "heading": heading,
                "anchor": slugify_heading(heading) if heading else "",
                "body": entry,
            }
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    if remaining_entries:
        log_path.write_text(_compose_system_log(preamble, remaining_entries), encoding="utf-8")
    else:
        log_path.write_text(f"{preamble}\n" if preamble else "", encoding="utf-8")

    decision_path = vault / decision_log
    if not decision_path.is_file():
        decision_path.write_text(
            "# Decision log\n\n"
            "Operator decisions migrated from `system/system-log.md` tails live in "
            f"`{events_out}` until promoted here.\n",
            encoding="utf-8",
        )

    return {
        "status": "migrated",
        "migrated_count": len(migrate_entries),
        "remaining_count": len(remaining_entries),
        "events_path": events_out,
        "decision_log_path": decision_log,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Split system log tail into events.jsonl.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--system-log", default=DEFAULT_SYSTEM_LOG)
    parser.add_argument("--events-out", default=DEFAULT_EVENTS)
    parser.add_argument("--decision-log", default=DEFAULT_DECISION_LOG)
    parser.add_argument(
        "--tail-entries",
        type=int,
        default=0,
        help="Migrate only the last N entries; 0 migrates all entries.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    result = migrate_system_log(
        vault,
        system_log=args.system_log,
        events_out=args.events_out,
        decision_log=args.decision_log,
        tail_entries=args.tail_entries,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] == "missing":
        print(display_path(vault, vault / args.system_log), "not found")
        return 0
    print(display_path(vault, vault / args.events_out))
    print(display_path(vault, vault / args.decision_log))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
