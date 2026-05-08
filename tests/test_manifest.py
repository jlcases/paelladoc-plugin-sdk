from __future__ import annotations

import json
from pathlib import Path

import pytest

from paelladoc_plugin_sdk import ManifestError, validate_plugin_dir


def write_plugin(root: Path, manifest: dict[str, object]) -> None:
    (root / "skills").mkdir(parents=True)
    (root / "methods").mkdir(parents=True)
    (root / "templates").mkdir(parents=True)
    (root / "skills" / "review.md").write_text("# Review\n", encoding="utf-8")
    (root / "templates" / "job.md").write_text("# Job\n", encoding="utf-8")
    (root / "methods" / "jtbd.json").write_text(
        json.dumps(valid_method_document()), encoding="utf-8"
    )
    (root / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")


def valid_method_document() -> dict[str, object]:
    return {
        "schema_version": "1",
        "method": {
            "key": "jtbd",
            "label": "Jobs To Be Done",
            "description": "A method for jobs, outcomes, and progress.",
            "artifact_types": [
                {
                    "key": "job_story",
                    "label": "Job Story",
                    "short_label": "JOB",
                    "canonical_type": "user_story",
                    "role": "work_item",
                    "template_path": "templates/job.md",
                },
                {
                    "key": "outcome",
                    "label": "Outcome",
                    "short_label": "OUT",
                    "canonical_type": "acceptance_criteria",
                    "role": "validation",
                },
            ],
            "navigation": {
                "sidebar_label": "Jobs",
                "group_label": "Job",
                "hierarchy_label": "Job Story -> Outcome",
                "tabs": [
                    {"key": "all", "label": "All", "roles": [], "artifact_types": []},
                    {
                        "key": "work",
                        "label": "Work",
                        "roles": ["work_item"],
                        "artifact_types": ["job_story"],
                    },
                ],
                "menu_items": [
                    {"key": "new_job_story", "label": "Job Story", "artifact_type": "job_story"}
                ],
            },
        },
    }


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


def test_rejects_method_pack_without_method_contribution(tmp_path: Path) -> None:
    manifest = base_manifest()
    manifest["plugin_type"] = "method_pack"
    manifest["contributes"] = {"skills": ["skills/review.md"]}
    write_plugin(tmp_path, manifest)

    with pytest.raises(ManifestError, match="must contribute at least one method"):
        validate_plugin_dir(tmp_path)


def test_rejects_method_with_invalid_canonical_type(tmp_path: Path) -> None:
    manifest = base_manifest()
    manifest["plugin_type"] = "method_pack"
    manifest["contributes"] = {"methods": ["methods/jtbd.json"]}
    write_plugin(tmp_path, manifest)
    method = valid_method_document()
    method["method"]["artifact_types"][0]["canonical_type"] = "user_stroy"
    (tmp_path / "methods" / "jtbd.json").write_text(json.dumps(method), encoding="utf-8")

    with pytest.raises(ManifestError, match="canonical_type must be one of"):
        validate_plugin_dir(tmp_path)


def test_rejects_method_menu_item_for_unknown_artifact_type(tmp_path: Path) -> None:
    manifest = base_manifest()
    manifest["plugin_type"] = "method_pack"
    manifest["contributes"] = {"methods": ["methods/jtbd.json"]}
    write_plugin(tmp_path, manifest)
    method = valid_method_document()
    method["method"]["navigation"]["menu_items"][0]["artifact_type"] = "ghost"
    (tmp_path / "methods" / "jtbd.json").write_text(json.dumps(method), encoding="utf-8")

    with pytest.raises(ManifestError, match="references unknown artifact type: ghost"):
        validate_plugin_dir(tmp_path)


@pytest.mark.parametrize(
    "example_dir",
    [
        "examples/product-method-pack",
        "examples/jtbd-method-pack",
        "examples/shape-up-method-pack",
        "examples/rfc-adr-method-pack",
    ],
)
def test_reference_method_packs_validate(example_dir: str) -> None:
    manifest = validate_plugin_dir(Path(example_dir))

    assert manifest.plugin_type == "method_pack"


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
