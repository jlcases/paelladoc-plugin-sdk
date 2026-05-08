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
METHOD_BODY_TEMPLATE_MAX_LEN = 64 * 1024

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
_METHOD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,79}$")

CANONICAL_ARTIFACT_TYPES = frozenset(
    {
        "prd",
        "epic",
        "user_story",
        "acceptance_criteria",
        "e2e_test",
        "design_task",
        "engineering_task",
        "technical_spec",
        "decision_record",
        "technical_debt",
        "product_debt",
        "improvement",
        "maintenance_task",
        "risk",
    }
)

ARTIFACT_ROLES = frozenset(
    {
        "problem",
        "scope",
        "work_item",
        "validation",
        "task",
        "decision",
        "risk",
        "debt",
        "maintenance",
        "release_gate",
    }
)


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

    plugin_type = _plugin_type(raw["plugin_type"])
    manifest = PluginManifest(
        schema_version=schema_version,
        plugin_id=plugin_id,
        plugin_type=plugin_type,
        name=_bounded_string(raw["name"], "name", max_len=80),
        version=version,
        publisher=_bounded_string(raw["publisher"], "publisher", max_len=80),
        license=_bounded_string(raw["license"], "license", max_len=40),
        description=_bounded_string(raw["description"], "description", max_len=400),
        permissions=permissions,
        contributes=contributes,
    )
    _validate_method_contributions(manifest, root=root)
    return manifest


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


def _validate_method_contributions(manifest: PluginManifest, *, root: Path) -> None:
    method_paths = manifest.contributes.get("methods", ())
    if manifest.plugin_type == "method_pack" and not method_paths:
        raise ManifestError("method_pack plugins must contribute at least one method")

    for method_path in method_paths:
        _validate_method_file(root / method_path, root=root, field=f"methods.{method_path}")


def _validate_method_file(path: Path, *, root: Path, field: str) -> None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"{field} contains invalid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise ManifestError(f"{field} must be a JSON object")
    _reject_unknown(raw, {"schema_version", "method", "methods"}, field)

    schema_version = _string(raw.get("schema_version"), f"{field}.schema_version")
    if schema_version != PLUGIN_SCHEMA_VERSION:
        raise ManifestError(f"{field}.schema_version must be {PLUGIN_SCHEMA_VERSION!r}")

    has_method = "method" in raw
    has_methods = "methods" in raw
    if has_method == has_methods:
        raise ManifestError(f"{field} must contain exactly one of method or methods")

    methods_raw = raw["methods"] if has_methods else [raw["method"]]
    if not isinstance(methods_raw, list) or not methods_raw:
        raise ManifestError(f"{field}.methods must be a non-empty list")

    keys: list[str] = []
    for index, method_raw in enumerate(methods_raw):
        key = _validate_method_definition(
            method_raw,
            root=root,
            field=f"{field}.methods[{index}]" if has_methods else f"{field}.method",
        )
        keys.append(key)
    _reject_duplicates(keys, f"{field}.methods[].key")


def _validate_method_definition(raw: Any, *, root: Path, field: str) -> str:
    method = _object(raw, field)
    _reject_unknown(
        method,
        {"key", "label", "description", "source", "artifact_types", "navigation"},
        field,
    )
    _require_fields(method, {"key", "label", "description", "artifact_types", "navigation"}, field)

    key = _method_identifier(method["key"], f"{field}.key")
    _bounded_string(method["label"], f"{field}.label", max_len=80)
    _bounded_string(method["description"], f"{field}.description", max_len=400)
    if "source" in method:
        _bounded_string(method["source"], f"{field}.source", max_len=360)

    artifact_type_keys = _validate_method_artifact_types(
        method["artifact_types"], root=root, field=f"{field}.artifact_types"
    )
    _validate_method_navigation(
        method["navigation"],
        artifact_type_keys=artifact_type_keys,
        field=f"{field}.navigation",
    )
    return key


def _validate_method_artifact_types(raw: Any, *, root: Path, field: str) -> frozenset[str]:
    artifact_types = _list(raw, field)
    if not artifact_types:
        raise ManifestError(f"{field} must contain at least one artifact type")

    keys: list[str] = []
    for index, item_raw in enumerate(artifact_types):
        item_field = f"{field}[{index}]"
        item = _object(item_raw, item_field)
        _reject_unknown(
            item,
            {
                "key",
                "label",
                "short_label",
                "canonical_type",
                "role",
                "description",
                "template_path",
                "body_template",
            },
            item_field,
        )
        _require_fields(item, {"key", "label", "short_label", "canonical_type", "role"}, item_field)

        key = _method_identifier(item["key"], f"{item_field}.key")
        keys.append(key)
        _bounded_string(item["label"], f"{item_field}.label", max_len=80)
        _bounded_string(item["short_label"], f"{item_field}.short_label", max_len=24)

        canonical_type = _method_identifier(item["canonical_type"], f"{item_field}.canonical_type")
        if canonical_type not in CANONICAL_ARTIFACT_TYPES:
            allowed = ", ".join(sorted(CANONICAL_ARTIFACT_TYPES))
            raise ManifestError(f"{item_field}.canonical_type must be one of: {allowed}")

        role = _string(item["role"], f"{item_field}.role")
        if role not in ARTIFACT_ROLES:
            allowed = ", ".join(sorted(ARTIFACT_ROLES))
            raise ManifestError(f"{item_field}.role must be one of: {allowed}")

        if "description" in item:
            _optional_bounded_string(item["description"], f"{item_field}.description", max_len=400)
        if "body_template" in item:
            _optional_bounded_string(
                item["body_template"],
                f"{item_field}.body_template",
                max_len=METHOD_BODY_TEMPLATE_MAX_LEN,
            )
        if "template_path" in item:
            template_value = _optional_bounded_string(
                item["template_path"], f"{item_field}.template_path", max_len=240
            )
            if template_value:
                _safe_existing_relative_path(root, template_value, f"{item_field}.template_path")

    _reject_duplicates(keys, f"{field}[].key")
    return frozenset(keys)


def _validate_method_navigation(
    raw: Any, *, artifact_type_keys: frozenset[str], field: str
) -> None:
    navigation = _object(raw, field)
    _reject_unknown(
        navigation,
        {"sidebar_label", "group_label", "hierarchy_label", "tabs", "menu_items"},
        field,
    )
    _require_fields(
        navigation,
        {"sidebar_label", "group_label", "hierarchy_label", "tabs", "menu_items"},
        field,
    )
    _bounded_string(navigation["sidebar_label"], f"{field}.sidebar_label", max_len=80)
    _bounded_string(navigation["group_label"], f"{field}.group_label", max_len=80)
    _bounded_string(navigation["hierarchy_label"], f"{field}.hierarchy_label", max_len=140)
    _validate_method_tabs(navigation["tabs"], artifact_type_keys=artifact_type_keys, field=f"{field}.tabs")
    _validate_method_menu_items(
        navigation["menu_items"],
        artifact_type_keys=artifact_type_keys,
        field=f"{field}.menu_items",
    )


def _validate_method_tabs(
    raw: Any, *, artifact_type_keys: frozenset[str], field: str
) -> None:
    tabs = _list(raw, field)
    if not tabs:
        raise ManifestError(f"{field} must contain at least one tab")

    keys: list[str] = []
    for index, tab_raw in enumerate(tabs):
        tab_field = f"{field}[{index}]"
        tab = _object(tab_raw, tab_field)
        _reject_unknown(tab, {"key", "label", "roles", "artifact_types"}, tab_field)
        _require_fields(tab, {"key", "label", "roles", "artifact_types"}, tab_field)
        keys.append(_method_identifier(tab["key"], f"{tab_field}.key"))
        _bounded_string(tab["label"], f"{tab_field}.label", max_len=80)

        for role_index, role_raw in enumerate(_list(tab["roles"], f"{tab_field}.roles")):
            role = _string(role_raw, f"{tab_field}.roles[{role_index}]")
            if role not in ARTIFACT_ROLES:
                allowed = ", ".join(sorted(ARTIFACT_ROLES))
                raise ManifestError(f"{tab_field}.roles[{role_index}] must be one of: {allowed}")

        for type_index, artifact_type_raw in enumerate(
            _list(tab["artifact_types"], f"{tab_field}.artifact_types")
        ):
            artifact_type = _method_identifier(
                artifact_type_raw, f"{tab_field}.artifact_types[{type_index}]"
            )
            if artifact_type not in artifact_type_keys:
                raise ManifestError(
                    f"{tab_field}.artifact_types[{type_index}] references unknown artifact type: "
                    f"{artifact_type}"
                )

    _reject_duplicates(keys, f"{field}[].key")


def _validate_method_menu_items(
    raw: Any, *, artifact_type_keys: frozenset[str], field: str
) -> None:
    menu_items = _list(raw, field)
    keys: list[str] = []
    for index, item_raw in enumerate(menu_items):
        item_field = f"{field}[{index}]"
        item = _object(item_raw, item_field)
        _reject_unknown(item, {"key", "label", "artifact_type"}, item_field)
        _require_fields(item, {"key", "label", "artifact_type"}, item_field)
        keys.append(_method_identifier(item["key"], f"{item_field}.key"))
        _bounded_string(item["label"], f"{item_field}.label", max_len=80)
        artifact_type = _method_identifier(item["artifact_type"], f"{item_field}.artifact_type")
        if artifact_type not in artifact_type_keys:
            raise ManifestError(
                f"{item_field}.artifact_type references unknown artifact type: {artifact_type}"
            )
    _reject_duplicates(keys, f"{field}[].key")


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


def _optional_bounded_string(raw: Any, field: str, *, max_len: int) -> str:
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise ManifestError(f"{field} must be a string")
    value = raw.strip()
    if len(value) > max_len:
        raise ManifestError(f"{field} is too long")
    return value


def _method_identifier(raw: Any, field: str) -> str:
    value = _bounded_string(raw, field, max_len=80)
    if not _METHOD_KEY_RE.fullmatch(value):
        raise ManifestError(f"{field} must be lowercase snake_case text")
    return value


def _object(raw: Any, field: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ManifestError(f"{field} must be an object")
    return raw


def _list(raw: Any, field: str) -> list[Any]:
    if not isinstance(raw, list):
        raise ManifestError(f"{field} must be a list")
    return raw


def _require_fields(raw: dict[str, Any], required: set[str], field: str) -> None:
    missing = sorted(required - raw.keys())
    if missing:
        raise ManifestError(f"{field} missing required fields: {', '.join(missing)}")


def _reject_unknown(raw: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ManifestError(f"{field} has unknown fields: {', '.join(unknown)}")


def _reject_duplicates(values: list[str], field: str) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        raise ManifestError(f"{field} must be unique: {', '.join(duplicates)}")


def _bool(raw: Any, field: str) -> bool:
    if not isinstance(raw, bool):
        raise ManifestError(f"{field} must be a boolean")
    return raw
