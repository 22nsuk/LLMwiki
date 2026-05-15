from __future__ import annotations

UTF8_COMPONENT_BYTE_LIMIT = 255
INFOZIP_C_LOCALE_COMPONENT_BYTE_LIMIT = 255


def utf8_byte_len(value: str) -> int:
    return len(value.encode("utf-8"))


def python_unicode_escape_byte_len(value: str) -> int:
    return len(value.encode("unicode_escape"))


def infozip_c_locale_escape(value: str) -> str:
    """Approximate Info-ZIP's C-locale Unicode component expansion."""
    parts: list[str] = []
    for char in value:
        codepoint = ord(char)
        if codepoint < 128:
            parts.append(char)
        elif codepoint <= 0xFFFF:
            parts.append(f"#U{codepoint:04x}")
        else:
            parts.append(f"#L{codepoint:08x}")
    return "".join(parts)


def infozip_c_locale_escape_byte_len(value: str) -> int:
    return len(infozip_c_locale_escape(value).encode("ascii"))


def infozip_c_locale_escape_path(path: str) -> str:
    return "/".join(
        infozip_c_locale_escape(component)
        for component in path.replace("\\", "/").split("/")
    )


def component_portability_metrics(component: str) -> dict[str, int]:
    return {
        "utf8_component_bytes": utf8_byte_len(component),
        "python_unicode_escape_component_bytes": python_unicode_escape_byte_len(component),
        "infozip_c_locale_escape_component_bytes": infozip_c_locale_escape_byte_len(component),
    }


def max_component_metric(path: str, metric_name: str) -> int:
    return max(
        (component_portability_metrics(component)[metric_name] for component in path.split("/")),
        default=0,
    )
