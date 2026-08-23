# Code intelligence toolset

AST-powered tools for **python, go, java and kotlin** (tree-sitter), with
Spring-aware discovery on the JVM side — and a generic surface: the language
is detected from the file extension, so one small toolset serves them all.

```bash
pip install "toolloop[code]"
```

```python
from toolloop.codetools import CODE_TOOLS  # = STD_TOOLS + AST tools

agent = Agent(provider, tools=CODE_TOOLS)
```

`AST_TOOLS` is also exported alone if you want it without the basic toolset.

## The tools

| Tool | What it does |
| --- | --- |
| `symbols(path)` | outline: kinds, names, line ranges (language by extension) |
| `find_symbol(name, root, kind=None)` | definition sites across a file tree |
| `references(symbol, root)` | identifier occurrences, excluding definitions |
| `imports(path)` | imports / package declaration of one file |
| `spring_endpoints(root)` | Spring REST map: verb, path, handler (java/kotlin) |
| `spring_beans(root)` | `@Component`/`@Service`/... classes and `@Bean` methods |

## Example

```text
symbols('controller.py') ->
  class      UserController  [1-3]
  function   UserController.index  [2-3]
  function   register_routes  [5-6]

find_symbol('UserController', root='.') ->
  controller.py:1  class
  com/example/UserController.java:3  class

spring_endpoints(root='.') ->
  GET     /api/users/{id}              UserController.get
```

## What it is (and is not)

tree-sitter is a **parser, not a semantic index**:

- `symbols`, `find_symbol`, `imports` and the Spring tools are structural and
  reliable.
- `references` is heuristic: it finds same-named identifiers excluding
  definition sites, but does not resolve imports or types. For semantic
  precision, language-server integration is on the roadmap — deliberately
  not a dependency of v1.

## Multi-language by extension

`.py` → python · `.go` → go · `.java` → java · `.kt`/`.kts` → kotlin.
Unsupported extensions return a clear error observation listing the
supported ones (the agent self-corrects to another tool).
