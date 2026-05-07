"""Manifest validation for PAELLADOC plugins.

The SDK validator intentionally stays dependency-free so plugin authors can run
it from a fresh Python install. The commercial app may add deeper checks, but it
must keep the same fail-closed contract.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PLUGIN_SCHEMA_VERSION = "1"
MANIFEST_FILE = "plugin.json"

ALLOWED_CONTRIBUTION_KEYS = frozenset(
    {
        "methods",
        "stacks",
        "skills",
        "mcp_servers",
        "engine_adapters",
        "templates",
        "validators",
        "panels",
        "commands",
    }
)

ALLOWED_PLUGIN_TYPES = frozenset(
    {
        "method_pack",
        "stack_pack",
        "agent_adapter",
        "mcp_pack",
        "validator_pack",
        "skill_pack",
    }
)

FORBIDDEN_CORE_KEYS = frozenset(
    {
        "kg",
        "knowledge_graph",
        "memory",
        "embeddings",
        "router",
        "ranking",
        "orchestration",
        "artifact_graph",
        "sync",
        "licensing",
        "updater",
    }
)

_PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{2,127}$")
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$")
_SHELL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,79}$")


class ManifestError(ValueError):
    """Raised when a plugin manifest violates the public contract."""


@dataclass(frozen=True)
class PluginManifest:
    schema_version: str
    plugin_id: str
    plugin_type: str
    name: str
    version: str
    publisher: str
    license: str
    description: str
    permissions: dict[str, Any]
    contributes: dict[str, tuple[Path, ...]]


def validate_plugin_dir(plugin_dir: str | Path) -> PluginManifest:
    root = Path(plugin_dir).expanduser().resolve()
    if not root.is_dir():
        raise ManifestError(f"Plugin directory not found: {root}")
    manifest_path = root / MANIFEST_FILE
    if not manifest_path.is_file():
        raise ManifestError(f"Missing {MANIFEST_FILE}")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"Invalid JSON: {exc}") from exc
    return validate_manifest_payload(raw, root=root)


def validate_manifest_payload(raw: Any, *, root: Path) -> PluginManifest:
    if not isinstance(raw, dict):
        raise ManifestError("Manifest must be a JSON object")

    required = {
        "schema_version",
        "id",
        "plugin_type",
        "name",
        "version",
        "publisher",
        "license",
        "description",
        "permissions",
        "contributes",
    }
    missing = sorted(required - raw.keys())
    if missing:
        raise ManifestError(f"Missing required fields: {', '.join(missing)}")

    schema_version = _string(raw["schema_version"], "schema_version")
    if schema_version != PLUGIN_SCHEMA_VERSION:
        raise ManifestError(f"Unsupported schema_version: {schema_version}")

    plugin_id = _string(raw["id"], "id")
    if not _PLUGIN_ID_RE.fullmatch(plugin_id) or ".." in plugin_id:
        raise ManifestError("id must be reverse-DNS style lowercase text")

    version = _string(raw["version"], "version")
    if not _VERSION_RE.fullmatch(version):
        raise ManifestError("version must be semantic version text like 0.1.0")

    permissions = _validate_permissions(raw["permissions"])
    contributes = _validate_contributions(raw["contributes"], root=root)

    return PluginManifest(
        schema_version=schema_version,
        plugin_id=plugin_id,
        plugin_type=_plugin_type(raw["plugin_type"]),
        name=_bounded_string(raw["name"], "name", max_len=80),
        version=version,
        publisher=_bounded_string(raw["publisher"], "publisher", max_len=80),
        license=_bounded_string(raw["license"], "license", max_len=40),
        description=_bounded_string(raw["description"], "description", max_len=400),
        permissions=permissions,
        contributes=contributes,
    )


def _validate_permissions(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ManifestError("permissions must be an object")
    allowed = {"repo_read", "repo_write", "network", "shell"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ManifestError(f"Unknown permission fields: {', '.join(unknown)}")

    repo_read = _bool(raw.get("repo_read", False), "permissions.repo_read")
    repo_write = _bool(raw.get("repo_write", False), "permissions.repo_write")
    network = raw.get("network", False)
    if isinstance(network, list):
        network = tuple(_bounded_string(item, "permissions.network[]", max_len=120) for item in network)
    elif isinstance(network, bool):
        pass
    else:
        raise ManifestError("permissions.network must be a boolean or list of hosts")

    shell_raw = raw.get("shell", ())
    if not isinstance(shell_raw, list):
        raise ManifestError("permissions.shell must be a list")
    shell: list[str] = []
    for item in shell_raw:
        command = _bounded_string(item, "permissions.shell[]", max_len=80)
        if not _SHELL_RE.fullmatch(command):
            raise ManifestError("permissions.shell entries must be command names, not shell snippets")
        if command not in shell:
            shell.append(command)

    return {
        "repo_read": repo_read,
        "repo_write": repo_write,
        "network": network,
        "shell": tuple(shell),
    }


def _plugin_type(raw: Any) -> str:
    value = _string(raw, "plugin_type")
    if value not in ALLOWED_PLUGIN_TYPES:
        allowed = ", ".join(sorted(ALLOWED_PLUGIN_TYPES))
        raise ManifestError(f"Unknown plugin_type: {value}. Expected one of: {allowed}")
    return value


def _validate_contributions(raw: Any, *, root: Path) -> dict[str, tuple[Path, ...]]:
    if not isinstance(raw, dict):
        raise ManifestError("contributes must be an object")
    forbidden = sorted(set(raw) & FORBIDDEN_CORE_KEYS)
    if forbidden:
        raise ManifestError(f"Closed-core contribution keys are forbidden: {', '.join(forbidden)}")
    unknown = sorted(set(raw) - ALLOWED_CONTRIBUTION_KEYS)
    if unknown:
        raise ManifestError(f"Unknown contribution keys: {', '.join(unknown)}")

    result: dict[str, tuple[Path, ...]] = {}
    for key, value in raw.items():
        if not isinstance(value, list):
            raise ManifestError(f"contributes.{key} must be a list")
        paths = tuple(_safe_existing_relative_path(root, item, f"contributes.{key}[]") for item in value)
        result[key] = paths
    return result


def _safe_existing_relative_path(root: Path, raw: Any, field: str) -> Path:
    value = _bounded_string(raw, field, max_len=240)
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ManifestError(f"{field} must stay inside the plugin directory")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ManifestError(f"{field} escapes the plugin directory") from exc
    if not resolved.is_file():
        raise ManifestError(f"{field} does not exist: {value}")
    return candidate


def _string(raw: Any, field: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ManifestError(f"{field} must be a non-empty string")
    return raw.strip()


def _bounded_string(raw: Any, field: str, *, max_len: int) -> str:
    value = _string(raw, field)
    if len(value) > max_len:
        raise ManifestError(f"{field} is too long")
    return value


def _bool(raw: Any, field: str) -> bool:
    if not isinstance(raw, bool):
        raise ManifestError(f"{field} must be a boolean")
    return raw
