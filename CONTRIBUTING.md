# Contributing

Thanks for helping improve AI Agent Collab Space. Open a GitLab issue for a focused bug report or proposal, or submit a merge request that explains the problem, changed behavior, and validation.

## Local development

Use Python 3.10 or later. The application uses the standard library. Keep root entrypoints compatible, and use a temporary workspace so development cannot modify a real board:

```sh
export COLLAB_WORKSPACE="/path/to/a/disposable/workspace"
python3 collab.py init
```

Use an appropriate environment assignment on Windows. Client accounts are optional for board development. Tests must not invoke paid model consultations, deliver real notifications, or alter global client settings.

## Verification

From the repository root:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tests/smoke_mcp.py mcp_server.py
```

The regression tests use isolated temporary state. Add meaningful cases for changed behavior, especially ownership checks, locks, transaction ordering, workspace selection, client configuration, and malformed MCP inputs. Consult the GitLab pipeline for the current automated checks.

Windows compatibility needs testing on Windows itself; a successful Linux test is not evidence that a Windows desktop shortcut or locking implementation works. State clearly which platforms you exercised.

## Change boundaries

- Keep source code and private runtime data separate.
- Preserve local-only defaults and avoid changing a user's global settings during setup.
- Use complete, committed snapshots and maintain compatible CLI/MCP behavior when practical.
- Treat model selection as configuration. Do not silently replace a named model.
- Document any new subprocess, notification destination, network listener, or write capability.
- Keep prompts, secrets, personal paths, account identifiers, live board contents, and generated test reports out of commits.

For multi-agent contributions, use the protocol in [AGENTS.md](AGENTS.md) only with a workspace intended for that collaboration. Do not make a read-only code review initialize or alter somebody else's board.

## Merge requests

Describe the user-visible change, why it is needed, how you tested it, and any limits. Include sanitized evidence when useful. Update the relevant guide and [CHANGELOG.md](CHANGELOG.md) for a meaningful feature or behavior change.

By contributing, you agree that your contribution is available under the project's [MIT License](LICENSE). Report security issues using [SECURITY.md](SECURITY.md), not a public issue containing exploit details or private data.
