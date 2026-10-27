# Claude contribution guidance

@AGENTS.md

The intended Claude model is Opus 5.5 with high effort. Model access and configuration belong to the installed client; this repository does not include account credentials.

Use generated client settings as a reviewed starting point. Do not replace global settings or silently switch a named model. The local consultation helper uses `claude-opus-5-5` with high effort; `COLLAB_CLAUDE_MODEL` can supply the provider's exact identifier while preserving that intended model.

When running as a one-off consultation with `COLLAB_HEADLESS=1`, answer the consultation directly. Do not check in as the live agent or post independently; the caller relays the result.

Use an authorized collaboration workspace for board operations and isolated temporary workspaces for testing. See [agent connections](docs/agents.md).
