# AGENTS.md

### Do
- After every change run typecheck with `uv run pyrefly check .` and fix type errors
- Format code with `format`
- Use src layout for code, see components/crawler_scheduler for example layout of a component
- Use union types over inheritence. Use tagged unions when data should be serailized
- Prefer match statements over if/else and other imperative constructs. Always do exhaustive matches

### Don't
- Add prod dependencies to root pyproject.toml, only dev.

### When stuck
- ask a clarifying question, propose a short plan

### Testing
- Write tests before writing code.
- Avoid using mocks unless absolutely necessary
- Use fixtures in integration tests for infrastructure dependencies like databases, logs and queues.
- Prefer methods over fixtures for other non-infra dependencies
- Use inline-snapshot for data assertions

