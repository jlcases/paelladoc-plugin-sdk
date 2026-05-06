# PAELLADOC Plugin SDK

Open SDK for building local-first PAELLADOC/CASIA plugins.

This repository is intentionally small and permissive. It contains the public
contracts developers need to extend PAELLADOC without exposing the closed core:
KG construction, memory retrieval, semantic ranking, router heuristics,
orchestration, licensing, updater, and privacy enforcement stay inside the app.

## What Plugins Can Contribute

- Skills and workflows.
- MCP server definitions.
- Agent engine adapters.
- Project templates.
- Validators such as test, lint, build, and release checks.
- Declarative panels in future versions.

## Plugin Types

- `method_pack`: PRD, epic, user story, acceptance criteria, and review methods.
- `stack_pack`: framework-specific templates, skills, and validators.
- `agent_adapter`: support for a coding agent CLI.
- `mcp_pack`: MCP server declarations and setup guidance.
- `validator_pack`: quality gates and release checks.
- `skill_pack`: reusable agent instructions and workflows.

## What Plugins Cannot Access

- Raw KG indexes.
- Embedding stores.
- Chat transcripts.
- Internal context planner.
- Router scoring.
- Artifact graph internals.
- Secrets or local settings unless the user explicitly grants them.

## Install For Development

```bash
python -m pip install -e .
```

## Validate A Plugin

```bash
paelladoc-plugin validate examples/aider-adapter
```

The validator fails closed: invalid manifests, unsafe paths, unknown
contribution keys, or closed-core access attempts are rejected.

## Minimal Manifest

```json
{
  "schema_version": "1",
  "id": "dev.example.my-plugin",
  "plugin_type": "skill_pack",
  "name": "My Plugin",
  "version": "0.1.0",
  "publisher": "Example",
  "license": "MIT",
  "description": "Adds local workflows for my stack.",
  "permissions": {
    "repo_read": true,
    "repo_write": false,
    "network": false,
    "shell": []
  },
  "contributes": {
    "skills": ["skills/review.md"]
  }
}
```

## License

Apache-2.0.
