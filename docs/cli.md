# CLI

Scaffold and validate projects. There is deliberately **no `toolloop run`** —
it is a library; execution lives in your code.

```bash
toolloop init my-agent   # scaffold (or `python -m toolloop init`)
toolloop check           # validate the declared tools/agent
```

## init — adaptive scaffolding

- **Empty folder** → full scaffold: `pyproject.toml` (with a
  `[tool.toolloop]` section), `agent.py` (demo agent with a scripted
  provider), `my_tools.py`, `tests/test_agent.py` (an offline scenario test),
  `README.md`, `.gitignore`.
- **Existing project** → only the missing pieces: the `[tool.toolloop]`
  section is appended to your `pyproject.toml` (or a minimal one is
  created), and a scenario test is added if there is no `tests/` yet.

`toolloop init` **never overwrites an existing file** — it reports what was
created and what was kept.

## check — validation

Reads the modules declared in `[tool.toolloop]` and validates:

- declared modules import cleanly
- no duplicate tool names
- tool schemas render into protocol instructions

```text
$ toolloop check
tools: 2
  look_up                  args=1
  search                   args=2 [dangerous]
agent module 'agent': imports OK
check passed
```

Non-zero exit on any problem — CI-friendly.

```toml
[tool.toolloop]
modules = ["my_tools"]   # modules whose tools `check` validates
agent = "agent"          # module that builds/exports your Agent (optional)
```
