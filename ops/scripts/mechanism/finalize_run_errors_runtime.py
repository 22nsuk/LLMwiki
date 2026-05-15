from __future__ import annotations


class FinalizeRunError(Exception):
    exit_code = 8


class FinalizeRunUsageError(FinalizeRunError):
    exit_code = 2


class FinalizeRunArtifactMissingError(FinalizeRunError):
    exit_code = 4


class FinalizeRunArtifactDecodeError(FinalizeRunError):
    exit_code = 5


class FinalizeRunArtifactSchemaError(FinalizeRunError):
    exit_code = 6


class FinalizeRunWriteError(FinalizeRunError):
    exit_code = 7
