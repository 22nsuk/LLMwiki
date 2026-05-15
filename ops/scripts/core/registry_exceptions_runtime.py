from __future__ import annotations

from pathlib import Path


class RawRegistryRuntimeError(Exception):
    diagnostic_type = "raw_registry_runtime_error"

    def diagnostic_detail(self) -> dict:
        return {
            "diagnostic_type": self.diagnostic_type,
            "message": str(self),
        }


class RawRegistryParseError(ValueError, RawRegistryRuntimeError):
    diagnostic_type = "raw_registry_parse_error"


class RawRegistryPageReadError(RawRegistryParseError):
    diagnostic_type = "raw_registry_page_read_failed"

    def __init__(self, path: Path, *, operation: str, reason: str) -> None:
        self.path = path.as_posix()
        self.operation = operation
        self.reason = reason
        super().__init__(f"failed to {operation} raw registry page {self.path}: {reason}")

    def diagnostic_detail(self) -> dict:
        detail = super().diagnostic_detail()
        detail.update({"path": self.path, "operation": self.operation})
        return detail


class RawRegistryEntryParseError(RawRegistryParseError):
    def __init__(self, registry_id: str, message: str) -> None:
        self.registry_id = registry_id
        super().__init__(message)

    def diagnostic_detail(self) -> dict:
        detail = super().diagnostic_detail()
        detail["registry_id"] = self.registry_id
        return detail


class RawRegistryEntryNoFieldsError(RawRegistryEntryParseError):
    diagnostic_type = "raw_registry_entry_no_fields"

    def __init__(self, registry_id: str) -> None:
        super().__init__(registry_id, f"raw registry entry {registry_id} has no fields")


class RawRegistryInvalidFieldLineError(RawRegistryEntryParseError):
    diagnostic_type = "raw_registry_invalid_field_line"

    def __init__(self, registry_id: str, line: str) -> None:
        self.line = line
        super().__init__(registry_id, f"invalid raw registry field line: {line}")

    def diagnostic_detail(self) -> dict:
        detail = super().diagnostic_detail()
        detail["line"] = self.line
        return detail


class RawRegistryLegacyCompactEntryError(RawRegistryEntryParseError):
    diagnostic_type = "raw_registry_legacy_compact_entry"

    def __init__(self, registry_id: str) -> None:
        super().__init__(
            registry_id,
            "legacy compact raw registry entries are unsupported; "
            "expand each field into its own bullet line",
        )


class RawRegistryInvalidContinuationLineError(RawRegistryEntryParseError):
    diagnostic_type = "raw_registry_invalid_continuation_line"

    def __init__(self, registry_id: str, line: str) -> None:
        self.line = line
        super().__init__(registry_id, f"invalid raw registry continuation line: {line}")

    def diagnostic_detail(self) -> dict:
        detail = super().diagnostic_detail()
        detail["line"] = self.line
        return detail


class RawRegistryYamlParseError(RawRegistryEntryParseError):
    diagnostic_type = "raw_registry_yaml_parse_error"

    def __init__(self, registry_id: str, reason: str) -> None:
        self.reason = reason
        super().__init__(registry_id, f"failed to parse raw registry entry {registry_id}: {reason}")


class RawRegistryInvalidPathAliasesError(RawRegistryParseError):
    diagnostic_type = "raw_registry_invalid_path_aliases"

    def __init__(self) -> None:
        super().__init__("raw registry field path_aliases must be a string or list of strings")


class RawRegistryRawFileReadError(RawRegistryRuntimeError):
    diagnostic_type = "raw_registry_raw_file_read_failed"

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path.as_posix()
        self.reason = reason
        super().__init__(f"failed to read raw file {self.path}: {reason}")

    def diagnostic_detail(self) -> dict:
        detail = super().diagnostic_detail()
        detail["path"] = self.path
        return detail


class RawRegistryExportEnrichmentLoadError(RawRegistryRuntimeError):
    diagnostic_type = "raw_registry_export_enrichment_load_failed"

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path.as_posix()
        self.reason = reason
        super().__init__(reason)

    def diagnostic_detail(self) -> dict:
        detail = super().diagnostic_detail()
        detail["path"] = self.path
        return detail


class RawRegistryExportInvalidJsonError(RawRegistryExportEnrichmentLoadError):
    diagnostic_type = "raw_registry_export_invalid_json"

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(path, f"invalid json: {reason}")


class RawRegistryExportReadError(RawRegistryExportEnrichmentLoadError):
    diagnostic_type = "raw_registry_export_read_failed"

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(path, f"read error: {reason}")


class RawRegistryExportShapeError(RawRegistryExportEnrichmentLoadError):
    diagnostic_type = "raw_registry_export_invalid_shape"

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(path, reason)


def raw_registry_exception_detail(exc: BaseException) -> dict:
    if isinstance(exc, RawRegistryRuntimeError):
        return exc.diagnostic_detail()
    return {
        "diagnostic_type": exc.__class__.__name__,
        "message": str(exc),
    }
