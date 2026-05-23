#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.command_runtime import run_with_timeout
    from ops.scripts.output_runtime import display_path, sanitize_report_text
    from ops.scripts.release.release_run_manifest import (
        build_manifest,
        git_clean,
        ignored_tracked_file_count,
        remote_sync,
        write_manifest,
    )
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )
else:
    from ops.scripts.command_runtime import run_with_timeout
    from ops.scripts.output_runtime import display_path, sanitize_report_text
    from ops.scripts.release.release_run_manifest import (
        build_manifest,
        git_clean,
        ignored_tracked_file_count,
        remote_sync,
        write_manifest,
    )
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )


DEFAULT_OUT = "build/release/release-run-manifest.json"
DEFAULT_TIMEOUT_SECONDS = 7200


def _tail(text: str, *, limit: int = 4000) -> str:
    return text if len(text) <= limit else text[-limit:]


def _command_step(
    *,
    vault: Path,
    name: str,
    command: list[str],
    expected_fingerprint: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    before = release_source_tree_fingerprint(vault)
    started = time.monotonic()
    result = run_with_timeout(command, cwd=vault, timeout_seconds=timeout_seconds)
    after = release_source_tree_fingerprint(vault)
    status = "pass" if result.returncode == 0 and not result.timed_out and after == expected_fingerprint else "fail"
    return {
        "name": name,
        "status": status,
        "command": [sanitize_report_text(vault, item) for item in command],
        "returncode": result.returncode,
        "duration_ms": int(round((time.monotonic() - started) * 1000)),
        "source_tree_fingerprint_before": before,
        "source_tree_fingerprint_after": after,
        "stdout_tail": sanitize_report_text(vault, _tail(result.stdout)),
        "stderr_tail": sanitize_report_text(vault, _tail(result.stderr)),
    }


def _synthetic_preflight(vault: Path, expected_fingerprint: str) -> dict[str, Any]:
    fingerprint = release_source_tree_fingerprint(vault)
    remote = remote_sync(vault)
    clean = git_clean(vault)
    ignored_count = ignored_tracked_file_count(vault)
    status = (
        "pass"
        if fingerprint == expected_fingerprint
        and clean
        and ignored_count == 0
        else "fail"
    )
    return {
        "name": "release-preflight-current",
        "status": status,
        "command": [],
        "returncode": 0 if status == "pass" else 1,
        "duration_ms": 0,
        "source_tree_fingerprint_before": fingerprint,
        "source_tree_fingerprint_after": fingerprint,
        "stdout_tail": (
            f"git_clean={clean}; remote_sync={remote['status']}; "
            f"ignored_tracked_file_count={ignored_count}"
        ),
        "stderr_tail": "",
    }


def _release_steps(make_bin: str) -> list[tuple[str, list[str]]]:
    return [
        ("release-test-current", [make_bin, "release-test-current"]),
        ("release-public-current", [make_bin, "release-public-current"]),
        ("release-package-current", [make_bin, "release-package-current"]),
        ("release-source-package-smoke", [make_bin, "release-source-package-smoke"]),
    ]


def run_release_ready(
    *,
    vault: Path,
    out_path: str,
    make_bin: str,
    timeout_seconds: int,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    expected = release_source_tree_fingerprint(vault)
    steps: list[dict[str, Any]] = [_synthetic_preflight(vault, expected)]
    if steps[-1]["status"] == "pass":
        for name, command in _release_steps(make_bin):
            step = _command_step(
                vault=vault,
                name=name,
                command=command,
                expected_fingerprint=expected,
                timeout_seconds=timeout_seconds,
            )
            steps.append(step)
            if step["status"] != "pass":
                break
    manifest = build_manifest(
        vault,
        expected_source_tree_fingerprint=expected,
        steps=steps,
        context=context or RuntimeContext(display_timezone=dt.timezone.utc),
    )
    write_manifest(vault, manifest, out_path)
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the single-authority release readiness workflow.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--make-bin", default="make")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    manifest = run_release_ready(
        vault=vault,
        out_path=args.out,
        make_bin=args.make_bin,
        timeout_seconds=args.timeout_seconds,
    )
    print(display_path(vault, (vault / args.out).resolve()))
    print(f"release_run_status={manifest['status']}")
    if manifest["failures"]:
        print("failures=" + ",".join(manifest["failures"]))
    return 0 if manifest["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover - direct script fallback
    raise SystemExit(main(sys.argv[1:]))
