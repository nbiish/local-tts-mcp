# Rules

## Coding Standards

- **Python**: Follow PEP 8.
- **Type Hints**: Use type hints for all function arguments and return values.
- **MCP**: Use `FastMCP` decorators for tools.

## Design Principles

- **Simplicity**: Keep tool interfaces minimal to reduce LLM token usage.
- **Privacy**: No external API calls for audio generation.
- **Performance**: Optimize for local execution (Apple Silicon preferred).
- **Dependency Management**: Use `uv` for all dependency handling.

## Commit Messages

- Follow Conventional Commits: `<type>(<scope>): <description>`
  - types: feat, fix, docs, refactor, test, chore
