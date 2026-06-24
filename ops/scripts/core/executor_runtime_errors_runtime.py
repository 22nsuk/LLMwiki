from __future__ import annotations


class ExecutorRuntimeError(Exception):
    exit_code = 8


class ExecutorRuntimeUsageError(ExecutorRuntimeError):
    exit_code = 2


class ExecutorRuntimeExecutionError(ExecutorRuntimeError):
    exit_code = 5
