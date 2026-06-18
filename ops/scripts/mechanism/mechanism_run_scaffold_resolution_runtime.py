from __future__ import annotations

import shlex
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.policy_runtime import (
    report_path,
    workspace_preparation_mode_from_policy,
)
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_constants_runtime import MUTATION_PROPOSAL_SCHEMA_PATH
from ops.scripts.core.schema_runtime import (
    load_schema_with_vault_override,
    validate_with_schema,
)

from .mechanism_assess import _dedupe_preserve_order, normalize_targets
from .mechanism_run_common_runtime import (
    CommandSpec,
    ExperimentResolution,
    RunMechanismExperimentArtifactError,
    RunMechanismExperimentUsageError,
    load_current_policy,
    load_json,
)
from .mechanism_run_scaffold_templates_runtime import default_log_summary

MUTATION_PROPOSAL_SCHEMA = MUTATION_PROPOSAL_SCHEMA_PATH
DEFAULT_MUTATION_PROPOSAL_REPORT = "ops/reports/mutation-proposals.json"
SHELL_CONTROL_TOKENS = {"&&", "||", "|", ";", "<", ">", ">>", "<<", "&", "2>", "2>>"}


@dataclass(frozen=True)
class PreparedExecutionCommands:
    mutation: CommandSpec
    check: CommandSpec


@dataclass(frozen=True)
class ProposalInputResolution:
    primary_targets: list[str]
    supporting_targets: list[str]
    proposal: dict | None
    proposal_source_report: str | None


@dataclass(frozen=True)
class ExperimentInputRequest:
    vault: Path
    run_id: str
    primary_targets: list[str]
    supporting_targets: list[str]
    test_files: list[str]
    scaffold_only: bool
    policy_path: str | None = None
    log_summary: str | None = None
    mutation_command: str | None = None
    check_command: str | None = None
    proposal_id: str | None = None
    proposal_report_path: str | None = None
    scope_freeze_path: str | None = None
    routing_report_paths: list[str] | None = None
    executor_report_paths: list[str] | None = None
    context: RuntimeContext | None = None


@dataclass(frozen=True)
class _ResolutionContext:
    policy: dict
    resolved_policy_path: Path
    policy_path_text: str
    runtime_context: RuntimeContext


def default_check_command(
    test_files: list[str] | None = None,
    *,
    workspace_mode: str = "full_copy",
) -> str:
    """Return the default repo-health command for the prepared workspace shape."""
    selectors = [str(path).strip() for path in test_files or [] if str(path).strip()]
    if workspace_mode == "sparse_manifest" and selectors:
        quoted_selectors = " ".join(shlex.quote(path) for path in selectors)
        return (
            f"{shlex.quote(sys.executable)} -B -m pytest "
            f"-p no:cacheprovider {quoted_selectors}"
        )
    return f"make PYTHON={shlex.quote(sys.executable)} check"


def resolve_command_executable(token: str, *, cwd: Path) -> str | None:
    if not token:
        return None
    if any(separator in token for separator in ("/", "\\")) or token.startswith("."):
        candidate = Path(token)
        check_path = candidate if candidate.is_absolute() else cwd / candidate
        if check_path.exists() and check_path.is_file():
            return str(candidate)
        return None
    return shutil.which(token)


def _strip_wrapping_quotes(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in {'"', "'"}:
        return token[1:-1]
    return token


def _resolve_tokenized_command(tokens: list[str], *, cwd: Path) -> list[str] | None:
    if not tokens:
        return None
    resolved = resolve_command_executable(tokens[0], cwd=cwd)
    if resolved is not None:
        return [resolved, *tokens[1:]]
    for end in range(2, len(tokens) + 1):
        candidate = " ".join(tokens[:end])
        resolved = resolve_command_executable(candidate, cwd=cwd)
        if resolved is not None:
            return [resolved, *tokens[end:]]
    return None


def command_argv(command: str, *, cwd: Path) -> list[str]:
    if not command.strip():
        raise RunMechanismExperimentUsageError("mutation/check command must not be empty")
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as exc:
        raise RunMechanismExperimentUsageError(f"invalid command syntax: {exc}") from exc
    if not tokens:
        raise RunMechanismExperimentUsageError("mutation/check command must not be empty")
    shell_controls = sorted({token for token in tokens if token in SHELL_CONTROL_TOKENS})
    if shell_controls:
        controls = ", ".join(shell_controls)
        raise RunMechanismExperimentUsageError(
            "shell operators are not supported in mutation/check commands "
            f"({controls}); put compound logic in a script and invoke that script directly"
        )
    resolved_tokens = _resolve_tokenized_command(tokens, cwd=cwd)
    if resolved_tokens is not None:
        return resolved_tokens
    if sys.platform == "win32":
        windows_tokens = [_strip_wrapping_quotes(token) for token in shlex.split(command, posix=False)]
        resolved_tokens = _resolve_tokenized_command(windows_tokens, cwd=cwd)
        if resolved_tokens is not None:
            return resolved_tokens
    return tokens


def prepare_execution_commands(
    *,
    mutation_command: str,
    check_command: str | None,
    cwd: Path,
    timeout_seconds: int,
    test_files: list[str] | None = None,
    workspace_mode: str = "full_copy",
) -> PreparedExecutionCommands:
    resolved_mutation_command = mutation_command.strip()
    resolved_check_command = (
        check_command or default_check_command(test_files, workspace_mode=workspace_mode)
    ).strip()
    return PreparedExecutionCommands(
        mutation=CommandSpec(
            command=resolved_mutation_command,
            argv=command_argv(resolved_mutation_command, cwd=cwd),
            timeout_seconds=timeout_seconds,
        ),
        check=CommandSpec(
            command=resolved_check_command,
            argv=command_argv(resolved_check_command, cwd=cwd),
            timeout_seconds=timeout_seconds,
        ),
    )


def load_mutation_proposal(
    vault: Path,
    *,
    proposal_id: str,
    proposal_report_path: str | None,
    policy: dict,
    resolved_policy_path: Path,
) -> tuple[dict, str]:
    rel_path = proposal_report_path or DEFAULT_MUTATION_PROPOSAL_REPORT
    report_path_abs = (vault / rel_path).resolve()
    payload = load_json(report_path_abs)
    schema = load_schema_with_vault_override(vault, MUTATION_PROPOSAL_SCHEMA)
    errors = validate_with_schema(payload, schema)
    if errors:
        raise RunMechanismExperimentArtifactError(
            f"mutation proposal report schema validation failed: {errors[0]}"
        )

    report_policy = payload.get("policy", {})
    expected_policy_path = report_path(vault, resolved_policy_path)
    if report_policy.get("path") != expected_policy_path:
        raise RunMechanismExperimentArtifactError(
            "mutation proposal report policy.path does not match current policy: "
            f"{report_policy.get('path')}"
        )
    if report_policy.get("version") != policy["version"]:
        raise RunMechanismExperimentArtifactError(
            "mutation proposal report policy.version does not match current policy: "
            f"{report_policy.get('version')}"
        )

    for proposal in payload.get("proposals", []):
        if proposal.get("proposal_id") == proposal_id:
            return proposal, report_path(vault, report_path_abs)
    raise RunMechanismExperimentUsageError(f"unknown proposal_id: {proposal_id}")


def normalize_target_rel_paths(vault: Path, raw_targets: list[str]) -> list[str]:
    try:
        return [rel_path for rel_path, _ in normalize_targets(vault, raw_targets)]
    except ValueError as exc:
        raise RunMechanismExperimentUsageError(str(exc)) from exc


def resolve_proposal_inputs(
    vault: Path,
    *,
    primary_targets: list[str],
    supporting_targets: list[str],
    proposal_id: str | None,
    proposal_report_path: str | None,
    policy: dict,
    resolved_policy_path: Path,
) -> ProposalInputResolution:
    resolved_primary_targets = normalize_target_rel_paths(
        vault,
        _dedupe_preserve_order(primary_targets),
    )
    resolved_supporting_targets = normalize_target_rel_paths(
        vault,
        _dedupe_preserve_order(supporting_targets),
    )

    proposal: dict | None = None
    proposal_source_report: str | None = None
    if proposal_id is not None:
        proposal, proposal_source_report = load_mutation_proposal(
            vault,
            proposal_id=proposal_id,
            proposal_report_path=proposal_report_path,
            policy=policy,
            resolved_policy_path=resolved_policy_path,
        )
        proposal_primary_targets = normalize_target_rel_paths(
            vault,
            _dedupe_preserve_order(list(proposal["primary_targets"])),
        )
        proposal_supporting_targets = normalize_target_rel_paths(
            vault,
            _dedupe_preserve_order(list(proposal["supporting_targets"])),
        )
        if resolved_primary_targets and resolved_primary_targets != proposal_primary_targets:
            raise RunMechanismExperimentUsageError(
                "explicit --primary-target values do not match the selected proposal primary_targets"
            )
        if resolved_supporting_targets and resolved_supporting_targets != proposal_supporting_targets:
            raise RunMechanismExperimentUsageError(
                "explicit --supporting-target values do not match the selected proposal supporting_targets"
            )
        if not resolved_primary_targets:
            resolved_primary_targets = proposal_primary_targets
        if not resolved_supporting_targets:
            resolved_supporting_targets = proposal_supporting_targets

    if not resolved_primary_targets:
        raise RunMechanismExperimentUsageError(
            "at least one --primary-target is required unless --proposal-id supplies the target set"
        )

    return ProposalInputResolution(
        primary_targets=resolved_primary_targets,
        supporting_targets=resolved_supporting_targets,
        proposal=proposal,
        proposal_source_report=proposal_source_report,
    )


def _experiment_input_request(
    vault_or_request: Path | ExperimentInputRequest,
    legacy_fields: dict[str, Any],
) -> ExperimentInputRequest:
    if isinstance(vault_or_request, ExperimentInputRequest):
        if legacy_fields:
            raise TypeError("resolve_experiment_inputs accepts either a request object or legacy keyword fields")
        return vault_or_request
    return ExperimentInputRequest(vault=vault_or_request, **legacy_fields)


def _resolution_context(request: ExperimentInputRequest) -> _ResolutionContext:
    policy, resolved_policy_path = load_current_policy(request.vault, request.policy_path)
    return _ResolutionContext(
        policy=policy,
        resolved_policy_path=resolved_policy_path,
        policy_path_text=report_path(request.vault, resolved_policy_path),
        runtime_context=request.context or RuntimeContext.from_policy(policy),
    )


def _resolved_log_summary(
    request: ExperimentInputRequest,
    proposal_resolution: ProposalInputResolution,
) -> str:
    return (request.log_summary or "").strip() or default_log_summary(
        request.run_id,
        proposal_resolution.primary_targets,
        proposal_resolution.proposal,
    )


def _prepared_commands(
    request: ExperimentInputRequest,
    policy: dict,
    resolved_test_files: list[str],
) -> PreparedExecutionCommands | None:
    if request.scaffold_only:
        return None
    if not (request.mutation_command or "").strip():
        raise RunMechanismExperimentUsageError("--mutation-command is required unless --scaffold-only is used")
    if not resolved_test_files:
        raise RunMechanismExperimentUsageError(
            "at least one --test-file is required for a full mechanism experiment run"
        )
    return prepare_execution_commands(
        mutation_command=request.mutation_command or "",
        check_command=request.check_command,
        cwd=request.vault,
        timeout_seconds=policy["auto_improve_policy"]["defaults"]["wrapper_command_timeout_seconds"],
        test_files=resolved_test_files,
        workspace_mode=workspace_preparation_mode_from_policy(policy),
    )


def _experiment_resolution(
    request: ExperimentInputRequest,
    context: _ResolutionContext,
    proposal_resolution: ProposalInputResolution,
    resolved_test_files: list[str],
    prepared_commands: PreparedExecutionCommands | None,
) -> ExperimentResolution:
    return ExperimentResolution(
        policy=context.policy,
        resolved_policy_path=context.resolved_policy_path,
        policy_path_text=context.policy_path_text,
        context=context.runtime_context,
        primary_targets=proposal_resolution.primary_targets,
        supporting_targets=proposal_resolution.supporting_targets,
        test_files=resolved_test_files,
        proposal=proposal_resolution.proposal,
        proposal_source_report=proposal_resolution.proposal_source_report,
        log_summary=_resolved_log_summary(request, proposal_resolution),
        mutation_command_spec=prepared_commands.mutation if prepared_commands else None,
        check_command_spec=prepared_commands.check if prepared_commands else None,
        scope_freeze_path=request.scope_freeze_path or "",
        routing_report_paths=list(request.routing_report_paths or []),
        executor_report_paths=list(request.executor_report_paths or []),
    )


def resolve_experiment_inputs(
    vault_or_request: Path | ExperimentInputRequest,
    **legacy_fields: Any,
) -> ExperimentResolution:
    request = _experiment_input_request(vault_or_request, legacy_fields)
    context = _resolution_context(request)
    proposal_resolution = resolve_proposal_inputs(
        request.vault,
        primary_targets=request.primary_targets,
        supporting_targets=request.supporting_targets,
        proposal_id=request.proposal_id,
        proposal_report_path=request.proposal_report_path,
        policy=context.policy,
        resolved_policy_path=context.resolved_policy_path,
    )
    resolved_test_files = normalize_target_rel_paths(
        request.vault,
        _dedupe_preserve_order(request.test_files),
    )
    prepared_commands = _prepared_commands(request, context.policy, resolved_test_files)
    return _experiment_resolution(request, context, proposal_resolution, resolved_test_files, prepared_commands)


_default_check_command = default_check_command
_resolve_command_executable = resolve_command_executable
_command_argv = command_argv
_prepare_execution_commands = prepare_execution_commands
_load_mutation_proposal = load_mutation_proposal
_normalize_target_rel_paths = normalize_target_rel_paths
_resolve_experiment_inputs = resolve_experiment_inputs
