from __future__ import annotations

import json
from pathlib import Path

import pytest

from paelladoc_plugin_sdk import ManifestError, validate_plugin_dir


def write_plugin(root: Path, manifest: dict[str, object]) -> None:
    (root / "skills").mkdir(parents=True)
    (root / "methods").mkdir(parents=True)
    (root / "skills" / "review.md").write_text("# Review\n", encoding="utf-8")
    (root / "methods" / "jtbd.json").write_text("{}", encoding="utf-8")
    (root / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")


def base_manifest() -> dict[str, object]:
    return {
        "schema_version": "1",
        "id": "dev.example.plugin",
        "plugin_type": "skill_pack",
        "name": "Example",
        "version": "0.1.0",
        "publisher": "Example",
        "license": "MIT",
        "description": "Example plugin.",
        "permissions": {
            "repo_read": True,
            "repo_write": False,
            "network": False,
            "shell": [],
        },
        "contributes": {"skills": ["skills/review.md"]},
    }


def test_valid_manifest(tmp_path: Path) -> None:
    write_plugin(tmp_path, base_manifest())

    manifest = validate_plugin_dir(tmp_path)

    assert manifest.plugin_id == "dev.example.plugin"
    assert manifest.plugin_type == "skill_pack"
    assert manifest.contributes["skills"] == (Path("skills/review.md"),)


def test_rejects_closed_core_contribution(tmp_path: Path) -> None:
    manifest = base_manifest()
    manifest["contributes"] = {"memory": ["skills/review.md"]}
    write_plugin(tmp_path, manifest)

    with pytest.raises(ManifestError, match="Closed-core"):
        validate_plugin_dir(tmp_path)


def test_accepts_method_contributions(tmp_path: Path) -> None:
    manifest = base_manifest()
    manifest["plugin_type"] = "method_pack"
    manifest["contributes"] = {"methods": ["methods/jtbd.json"]}
    write_plugin(tmp_path, manifest)

    loaded = validate_plugin_dir(tmp_path)

    assert loaded.plugin_type == "method_pack"
    assert loaded.contributes["methods"] == (Path("methods/jtbd.json"),)


def test_rejects_path_traversal(tmp_path: Path) -> None:
    manifest = base_manifest()
    manifest["contributes"] = {"skills": ["../secret.md"]}
    write_plugin(tmp_path, manifest)

    with pytest.raises(ManifestError, match="inside the plugin directory"):
        validate_plugin_dir(tmp_path)


def test_rejects_shell_snippet_permission(tmp_path: Path) -> None:
    manifest = base_manifest()
    manifest["permissions"] = {"shell": ["aider && rm -rf ."]}
    write_plugin(tmp_path, manifest)

    with pytest.raises(ManifestError, match="command names"):
        validate_plugin_dir(tmp_path)


def test_rejects_unknown_plugin_type(tmp_path: Path) -> None:
    manifest = base_manifest()
    manifest["plugin_type"] = "brain_plugin"
    write_plugin(tmp_path, manifest)

    with pytest.raises(ManifestError, match="Unknown plugin_type"):
        validate_plugin_dir(tmp_path)
