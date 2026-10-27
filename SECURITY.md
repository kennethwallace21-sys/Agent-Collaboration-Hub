# Security policy

## Reporting a vulnerability

Use a confidential GitLab issue when the project offers that option. If confidential reporting is unavailable, open an issue requesting a private reporting channel without posting the exploit, credentials, board data, or personal logs. No separate security email address is published by this project.

Provide a minimal, sanitized reproduction, the affected source revision, operating system, Python version, and the expected security boundary. Use a disposable workspace and synthetic content.

## Scope and support

This is a locally operated collaboration tool for trusted participants. It is not an authenticated public service. File locks and board identities support coordination; they do not provide a security sandbox or prove who sent a message.

Keep the dashboard bound to loopback and review the tools enabled for each agent. A separately hosted remote integration requires its own security design. The latest source is the maintained baseline; no long-term support or response-time commitment is currently published.

See [security and privacy](docs/security.md) for data handling, model-provider boundaries, backups, and publishing guidance.
