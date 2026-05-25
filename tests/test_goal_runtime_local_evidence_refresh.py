from __future__ import annotations

import tempfile
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path

from ops.scripts.command_runtime import TimedProcessResult

from ops.scripts.mechanism.goal_runtime_local_evidence_refresh import (
    DEFAULT_TARGET_SEQUENCE,
    GoalRuntimeLocalEvidenceRefreshRequest,
    run_refresh,
)


def _result(argv: Sequence[str], *, stdout: str = "") -> TimedProcessResult:
    return TimedProcessResult(
        args=list(argv),
        returncode=0,
        stdout=stdout,
        stderr="",
        timed_out=False,
        timeout_seconds=30,
        termination_reason="",
    )


class GoalRuntimeLocalEvidenceRefreshTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name)
        self.paths = (
            "runs/goal-test/state/codex-goal-contract.json",
            "runs/goal-test/state/goal-run-status.json",
            "runs/goal-test/state/auto-improve-readiness.json",
            "runs/goal-test/state/session-synopsis.json",
            "runs/goal-test/state/self-improvement-negative-lessons.json",
            "runs/goal-test/state/remediation-backlog.json",
        )
        for index, relative_path in enumerate(self.paths):
            path = self.vault / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f'{{"stable": {index}}}\n', encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _request(self, *, max_iterations: int = 4) -> GoalRuntimeLocalEvidenceRefreshRequest:
        return GoalRuntimeLocalEvidenceRefreshRequest(
            vault=self.vault,
            python_executable=".venv/bin/python",
            max_iterations=max_iterations,
            timeout_seconds=30,
            tracked_paths=self.paths,
        )

    def test_stops_after_one_iteration_when_outputs_are_already_stable(self) -> None:
        calls: list[str] = []
        observed_env: list[str] = []

        def runner(
            argv: Sequence[str],
            cwd: Path,
            timeout_seconds: int,
            env: Mapping[str, str],
        ) -> TimedProcessResult:
            self.assertEqual(cwd, self.vault)
            self.assertEqual(timeout_seconds, 30)
            calls.append(argv[1])
            observed_env.append(env["LLMWIKI_RUNTIME_UTC_NOW"])
            return _result(argv)

        report = run_refresh(
            self._request(),
            command_runner=runner,
            base_env={},
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["reason"], "converged")
        self.assertEqual(report["summary"]["iteration_count"], 1)
        self.assertEqual(calls, list(DEFAULT_TARGET_SEQUENCE))
        self.assertEqual(len(set(observed_env)), 1)

    def test_reruns_until_digest_fixed_point_is_reached(self) -> None:
        calls: list[str] = []
        changed = False

        def runner(
            argv: Sequence[str],
            cwd: Path,
            timeout_seconds: int,
            env: Mapping[str, str],
        ) -> TimedProcessResult:
            nonlocal changed
            calls.append(argv[1])
            if argv[1] == "goal-runtime-local-remediation-backlog" and not changed:
                (self.vault / self.paths[-1]).write_text('{"stable": "after-refresh"}\n', encoding="utf-8")
                changed = True
            return _result(argv)

        report = run_refresh(
            self._request(),
            command_runner=runner,
            base_env={"LLMWIKI_RUNTIME_UTC_NOW": "2026-05-21T16:00:00Z"},
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["iteration_count"], 2)
        self.assertEqual(report["summary"]["converged_iteration"], 2)
        self.assertEqual(calls, list(DEFAULT_TARGET_SEQUENCE) * 2)
        self.assertEqual(report["generated_at"], "2026-05-21T16:00:00Z")

    def test_ignores_envelope_fingerprint_churn_for_semantic_fixed_point(self) -> None:
        counter = 0
        for relative_path in self.paths:
            (self.vault / relative_path).write_text(
                '{"generated_at": "2026-05-21T16:00:00Z", "source_tree_fingerprint": "before", "semantic": "stable"}\n',
                encoding="utf-8",
            )

        def runner(
            argv: Sequence[str],
            cwd: Path,
            timeout_seconds: int,
            env: Mapping[str, str],
        ) -> TimedProcessResult:
            nonlocal counter
            counter += 1
            for relative_path in self.paths:
                (self.vault / relative_path).write_text(
                    (
                        "{"
                        f'"generated_at": "2026-05-21T16:00:{counter:02d}Z", '
                        f'"source_tree_fingerprint": "volatile-{counter}", '
                        '"semantic": "stable"'
                        "}\n"
                    ),
                    encoding="utf-8",
                )
            return _result(argv)

        report = run_refresh(
            self._request(),
            command_runner=runner,
            base_env={},
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["iteration_count"], 1)
        self.assertEqual(
            report["digest_mode"], "semantic_without_envelope_fingerprints_or_clock_fields"
        )

    def test_ignores_goal_status_clock_fields_for_semantic_fixed_point(self) -> None:
        counter = 0
        self.assertEqual(self.paths[1], "runs/goal-test/state/goal-run-status.json")
        (self.vault / self.paths[1]).write_text(
            (
                "{"
                '"run": {"started_at": "2026-05-21T16:00:00Z", '
                '"updated_at": "2026-05-21T16:00:00Z", "status": "blocked"}, '
                '"observability": {'
                '"last_heartbeat_at": "2026-05-21T16:00:00Z", '
                '"last_checkpoint_at": "2026-05-21T16:00:00Z"}, '
                '"periodic_evidence": {"checkpoints": ['
                '{"due_at": "2026-05-21T17:00:00Z", "due_after_seconds": 3600}'
                "]}"
                "}\n"
            ),
            encoding="utf-8",
        )

        def runner(
            argv: Sequence[str],
            cwd: Path,
            timeout_seconds: int,
            env: Mapping[str, str],
        ) -> TimedProcessResult:
            nonlocal counter
            counter += 1
            (self.vault / self.paths[1]).write_text(
                (
                    "{"
                    f'"run": {{"started_at": "2026-05-21T16:00:{counter:02d}Z", '
                    f'"updated_at": "2026-05-21T16:00:{counter:02d}Z", '
                    '"status": "blocked"}, '
                    '"observability": {'
                    f'"last_heartbeat_at": "2026-05-21T16:00:{counter:02d}Z", '
                    f'"last_checkpoint_at": "2026-05-21T16:00:{counter:02d}Z"}}, '
                    '"periodic_evidence": {"checkpoints": ['
                    f'{{"due_at": "2026-05-21T17:00:{counter:02d}Z", '
                    '"due_after_seconds": 3600}'
                    "]}"
                    "}\n"
                ),
                encoding="utf-8",
            )
            return _result(argv)

        report = run_refresh(
            self._request(),
            command_runner=runner,
            base_env={"LLMWIKI_RUNTIME_UTC_NOW": "2026-05-21T16:00:00Z"},
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["iteration_count"], 1)
        self.assertIn("run.started_at", report["semantic_volatile_paths"])

    def test_fails_when_outputs_keep_changing_after_iteration_budget(self) -> None:
        counter = 0

        def runner(
            argv: Sequence[str],
            cwd: Path,
            timeout_seconds: int,
            env: Mapping[str, str],
        ) -> TimedProcessResult:
            nonlocal counter
            if argv[1] == "goal-runtime-local-remediation-backlog":
                counter += 1
                (self.vault / self.paths[-1]).write_text(f'{{"counter": {counter}}}\n', encoding="utf-8")
            return _result(argv)

        report = run_refresh(
            self._request(max_iterations=2),
            command_runner=runner,
            base_env={},
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["reason"], "not_converged")
        self.assertEqual(report["summary"]["iteration_count"], 2)
        self.assertFalse(report["converged"])


if __name__ == "__main__":
    unittest.main()
