# Plano de implementação — toolloop v0.1.0 (atualizado)

Mesmo plano aprovado, com o ajuste de granularidade dos modos de controle: **ControlMode com exatamente 2 opções — `APPROVE` (default-deny: toda tool call precisa ser liberada por um hook `on_tool_call`) e `BYPASS` (default-allow: autônomo, hooks ainda podem vetar/modificar)**. Sem modo intermediário. A renomeação da pasta `~/Projects/openFlow` → `~/Projects/toolloop` está confirmada no scaffold.

## 1. Scaffold e identidade

- Renomear pasta (levando `brainstorms/`), `git init -b main`, atualizar o brainstorm com a decisão dos 2 modos (fonte da verdade).
- `pyproject.toml` (hatchling): `toolloop` 0.1.0, **Python ≥3.11**, runtime dep única **pydantic ≥2**; dev: `pytest`, `pytest-asyncio`, `ruff`. Gerenciado com **uv**. **MIT**.
- Layout `src/`: `_types` (mensagens, exceções, Status), `provider` (Protocol async), `tools/` (`definition.py` com `@tool` + std toolset `shell/fs/search`), `protocol/` (`base.py` ABC + `json_protocol.py`), `agent` (loop + RunResult), `hooks` (3 hooks + ControlMode), `context` (truncation + compaction), `subagent`, `examples/`, `tests/`.

## 2. Contratos centrais

```python
class Provider(Protocol):
    async def complete(self, messages: Sequence[Message]) -> str: ...

@tool  # async fn; nome=função, desc=docstring, schema via type hints (pydantic)

class Agent:
    def __init__(self, provider, tools=(), *, protocol=None, system_prompt=None,
                 control=ControlMode.BYPASS, on_step=None, on_tool_call=None,
                 on_tool_result=None, max_context_tokens=None): ...
    async def run(self, input, *, max_iterations=25, on_max=OnMax.RAISE,
                  control=None, output_model=None) -> RunResult
# RunResult: output (validado se output_model), status (COMPLETED|MAX_ITERATIONS), history completo
```

- Envelope JSON: `{"type":"tool_call","calls":[{id?,name,args}]}` | `{"type":"final_answer","output":...}`; parse tolerante (fenced/cru, último bloco válido vence); auto-repair com limite de falhas consecutivas; calls executadas **sequencialmente**.
- Hooks: `on_step`/`on_tool_call`→`Decision.allow/deny`/`on_tool_result`; BYPASS mantém observabilidade; APPROVE sem hook `on_tool_call` → erro de configuração claro no `run()`.
- Contexto: heurística chars/4; truncation de observações antigas; compaction via sumarização pelo próprio provider (preserva system + mensagens recentes); safety-net de tamanho por resultado; toolset com resultados compactos por design.
- `subagent_tool(agent)` no core; toolset padrão com `bash` marcada `dangerous`.

## 3. Milestones (commits por grupo)

1. Scaffold + config + git
2. Core (`_types`, `provider`, `tools`)
3. `protocol/json_protocol`
4. `agent` (loop, políticas de max_iterations, histórico)
5. `hooks` + ControlMode APPROVE/BYPASS
6. `context` + `subagent`
7. Toolset padrão (6 tools)
8. `examples/` + README real
9. Suite de testes (FakeProvider scriptado: happy path, auto-repair, veto, modos, políticas de estouro, compaction, subagent, tools em tmp_path) + ruff limpo + tag `v0.1.0`

## 4. Fora do escopo v1 (roadmap no README)

Streaming, tool calls paralelas, CLI (`init`/`test`), adapters publicados como extras.