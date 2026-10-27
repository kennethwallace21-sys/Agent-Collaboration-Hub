# Client configuration examples

Run the generator from your source or installed app folder:

```sh
python3 setup_clients.py --workspace /absolute/path/to/your-workspace
```

It writes machine-local configuration into `WORKSPACE/client-configs/`. These generated files contain your Python executable, installed code location, and shared workspace path. Review and merge only the relevant entries into your client; existing settings and credentials are never changed automatically.

| Generated file | Destination / purpose |
| --- | --- |
| `claude.mcp.json` | Claude Code project `.mcp.json` |
| `claude.settings.json` | Claude Code project `.claude/settings.json`; exact Opus 5.5, High, and optional alert hooks |
| `codex.toml` | Merge `[mcp_servers.agent-collab]` into the Codex host config |
| `codex.hooks.json` | Codex workspace `.codex/hooks.json`; client trust may be required |
| `antigravity.mcp.json` | Merge server into Antigravity MCP settings |
| `antigravity.hooks.json` | Merge optional alert hooks into Antigravity workspace settings |

All clients must use the **same** `COLLAB_WORKSPACE`. Keep generated files private and out of source control. Model clients require their own installed software, accounts, supported model access, and any applicable usage credits. See [agent setup](../docs/agents.md).
