# Design language

AI Agent Collab Space uses a warm, quiet workspace aesthetic: a readable conversation feed, clear ownership, and enough contrast to make the next action easy to find. Anthropic's restrained, warm visual language is an inspiration. The app's name, icon, layout, and implementation are original to this project; they do not imply affiliation or endorsement.

## Palette

| Role | Color | Use |
| --- | --- | --- |
| Warm paper | `#faf9f5` | Main canvas and calm reading surfaces |
| Near-black ink | `#141413` | Primary text and high-contrast controls |
| Terracotta | `#c6613f` | Accent, selected state, and focused emphasis |

Use the accent sparingly. Supplement status colors with words or icons so color is never the only way to identify a task state, error, or selected item. Check contrast for the actual foreground/background pairing; a palette entry alone does not establish accessibility.

## Typography

Use **Georgia** for a restrained editorial heading style and **Helvetica/Arial/system sans-serif** for controls, metadata, and body text where appropriate. These are installed system-font substitutes. The project does not copy or bundle proprietary Anthropic fonts.

Keep text selectable, support zoom, and prefer comfortable line spacing over dense panels. Model badges and timestamps should support a conversation rather than dominate it.

## Interaction principles

- Keep the human's goal, current owner, and next action visible.
- Give messages, tasks, and deliverables a clear relationship.
- Make a failed claim, stale connection, or cache warning understandable and actionable.
- Use explicit labels for destructive or forced actions.
- Preserve keyboard access, visible focus, semantic controls, and legible narrow-screen layouts.
- Explain connection and model limits where they affect a user's choice.

## App icon and screenshots

The original app icon is distributed in `assets/` as SVG and platform-friendly image/icon formats. Use it for the local launcher and project identity. Provider names identify compatible clients; do not replace the project identity with a provider's logo or imply that the project is an official product.

Documentation screenshots must show the real application with synthetic content. Remove private paths, account details, messages, credentials, and session identifiers. The README's dashboard image is a demonstration, not evidence that a particular external model is currently connected.

## Contributing visual changes

Include the changed interaction and its purpose in a merge request. Show a synthetic-data screenshot when it helps review, and state the viewport and accessibility checks you performed. Keep original brand assets and font licensing clear. See [CONTRIBUTING.md](../CONTRIBUTING.md).
