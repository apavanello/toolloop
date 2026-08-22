# toolloop — Framework Python de agent loop sem tool use nativo: Brainstorm / Discovery Notes
Date: 2026-08-22 · Goal: Definir um framework Python que facilite a criação de ferramentas/agentes que usam IA, onde o provider (abstraido) não suporta tool use nativamente.

## Summary / key decisions
- **O que é**: framework de **agent loop** (harness de agente autônomo, estilo Claude Code), não só emulação de tool use. Loop central: dada uma entrada X, o modelo usa as tools disponíveis em loop (uso ferramental, exploratório e codificatório) **até ficar satisfeito**, produzindo a saída final.
- **Problema real**: SDKs privativos corporativos que fazem proxy de providers grandes (Anthropic, OpenAI, Kimi, DeepSeek etc.) mas têm uma camada corporativa que **não expõe tools use** ("OpenRouter corporativo"). Modelos por trás são fortes; a limitação é do SDK.
- **Provider**: framework **não gerencia providers**. Contrato mínimo async: `async def complete(messages) -> str` (Protocol). Sem streaming no contrato v1. Usuário traz SDK próprio/código próprio. Adapters OpenAI-compatível e Anthropic apenas como `examples/`, não dependência.
- **Protocolo de tools plugável** (renderizador de system prompt + parser de saída); default = **bloco JSON**; **auto-repair**: erro de parse/validação volta ao modelo como observação.
- **Envelope explícito com discriminador**: `{"type": "tool_call", "calls": [...], ...}` ou `{"type": "final_answer", "output": ...}`. Loop termina só com `final_answer` (pode carregar saída estruturada validada). Campo `calls` é lista desde o v1 (forward-compatible), mas **v1 executa sequencialmente**; paralelização no roadmap. `max_iterations` configurável com política de estouro (erro / forçar wrap-up / retornar parcial com status).
- **Definição de tools**: `@tool` em funções **async**; nome = função, descrição = docstring, schema via type hints + **pydantic** (validação alimenta auto-repair). Retorno `str` ou serializável; exceções viram observação de erro por padrão (configurável).
- **Toolset opcional** `toolloop.tools`: `bash`, `read_file`, `write_file`, `edit_file`, `grep`/`search`, `list_files`. Core permanece agnóstico.
- **Hooks async de primeira classe**: `on_step` (por turno), `on_tool_call` (pré-execução; veto/modificação/aprovação → human-in-the-loop), `on_tool_result` (pós-execução). Resultado de `run()` carrega histórico completo.
- **Modos de controle: exatamente 2** (decisão final do usuário ao aprovar o plano) — `APPROVE` (default-deny: toda tool call precisa ser liberada pelo hook `on_tool_call`) e `BYPASS` (default-allow: autônomo; hooks ainda podem vetar/modificar). Configuráveis na instanciação e sobrescrevíveis no `run()`. Sem modo intermediário.
- **Gestão de contexto como harnesses modernos**: `max_context_tokens` opcional com truncation de tool results antigos + compaction por sumarização; resultados de tools **compactos por design** (confiança na sub-execução, estilo a2a); safety-net de tamanho por resultado; tool **`subagent` no core v1** (contexto isolado, devolve só `final_answer`).
- **Identidade**: nome **toolloop** (PyPI livre, sem colisões conceituais — `openloop` colide com thu-nmrc/openloop; `openflow` colide com projeto SDN de rede). **Open source, MIT**. Python 3.11+, pyproject + uv, pytest com provider fake em memória, ruff. v1 é **library pura** (sem CLI); roadmap: CLI básico (`init`, `test`, etc.).

## Q&A log
### Q0 — contexto adicional (antes da Q1)
- Asked: (usuário forneceu contexto espontaneamente)
- Captured: "simular o comportamento de agentes autônomos como harnesses ou claws" — facilitar o loop de uso ferramental, exploratório e codificatório; dado input X, o modelo usa as tools em loop até ficar satisfeito e provê a saída.
- Flags: interpretação "harnesses/claws" = agentes estilo Claude Code — **resolvida implicitamente** pelas respostas seguintes (toolset coding, modos de controle, "como harnesses modernos fazem").

### Q1 — Providers alvo / quem gerencia o provider
- Asked: Quais providers/modelos concretos suportar primeiro? Foco em endpoints OpenAI-compatible?
- Captured: Compatível com OpenAI Chat Completions e Anthropic **como referência**, mas o framework **não deve gerenciar o provider diretamente**. O utilizador fica livre para usar o provider que desejar — SDK próprio ou código próprio.
- Decisão: core 100% provider-agnostic; só um contrato mínimo (mensagens → texto), sem depender de nenhum SDK.
- Flags: adaptadores prontos opcionais → **resolvido na Q10** (examples/, não dependência).

### Q2 — Contrato do provider (sync/async, streaming)
- Asked: Contrato síncrono ou assíncrono? Streaming no contrato mínimo?
- Captured: "async então" — confirmado **async-first**.
- Decisão: Protocol async único (`async def complete(messages) -> str`). Streaming fora do contrato v1 (extensão futura).

### Q3 — Formato da tool call emulado + parsing
- Asked: Como o modelo expressa tool call em texto (ReAct / JSON / XML)? Plugável?
- Captured: Confirmou plugável + JSON default + auto-repair. Contexto adicional: alvo **não** são modelos pequenos — são **SDKs privativos corporativos** proxyando providers grandes sem expor tools use ("OpenRouter corporativo").
- Decisão: protocolo de tools plugável (par system-prompt-renderer + output-parser); default = bloco JSON; auto-repair devolve erros de parse/validação como observação. Modelos fortes → JSON de primeira é o caso comum.

### Q4 — Condição de parada e saída final
- Asked: Envelope explícito com discriminador vs. ausência de tool call = final (ReAct)?
- Captured: "confirmo".
- Decisão: envelope JSON com `type` — `tool_call` ou `final_answer` (com saída estruturada validada). Loop termina só com `final_answer`. `max_iterations` com política configurável (erro / wrap-up forçado / parcial com status).

### Q5 — API de definição de tools
- Asked: Decorator + type hints + pydantic, ou zero-dep com schema manual?
- Captured: "Sim".
- Decisão: `@tool` em funções async; schema por type hints via pydantic (gera JSON schema do prompt e valida args → alimenta auto-repair). Retorno `str`/serializável; exceções → observação de erro por padrão. Pydantic no core.

### Q6 — Toolset embutido vs. tools só do utilizador
- Asked: Framework embarca tools prontas? Quais?
- Captured: "Sim pode incluir".
- Decisão: core agnóstico; módulo opcional `toolloop.tools` com `bash`, `read_file`, `write_file`, `edit_file`, `grep`/`search`, `list_files`.

### Q7 — Hooks de observabilidade/controle + histórico
- Asked: Confirmar 3 hooks + histórico completo no resultado?
- Captured: "Sim, porém importante ter a opção (na chamada ou no instanciamento) de **bypass ou Full Control**".
- Decisão: hooks `on_step` / `on_tool_call` (veto/modifica/aprova) / `on_tool_result`; histórico completo no resultado. **Modos de controle** bypass ↔ full control, configuráveis na instanciação e/ou no `run()`; níveis intermediários possíveis (ex.: aprovar só tools perigosas).
- Flags: nome/enum dos modos e granularidade (por tool? categoria?) -> definir na implementação.

### Q8 — Gestão de contexto / tamanho do histórico
- Asked: v1 sem gestão, truncation, ou compaction?
- Captured: "como harnesses modernos fazem" + ideia própria: chamada de tool quase **a2a**, separada do contexto principal, retornando só o relevante (tool de escrita não retorna o que escreveu) — "confiança na sub-execução" (usuário duvidava que fosse funcional).
- Decisão: truncation de tool results antigos + compaction por sumarização (`max_context_tokens` opcional). Ideia a2a **aceita** (é o pattern sub-agent de harnesses reais): (1) toolset retorna compacto por design; (2) safety-net de tamanho por resultado; (3) tool `subagent` com contexto isolado devolvendo só `final_answer`.

### Q9 — Identidade e distribuição (nome, OSS, licença, tooling)
- Asked: Nome? Open source? Licença?
- Captured: nome proposto "openloop" (pasta openFlow foi criada errada — openflow já existe no mercado); aberto a sugestões; OSS "que pede apenas créditos".
- Checagem: PyPI — `openloop` e `toolloop` livres; `open-loop`, `agentloop`, `loopkit`, `pyopenloop` ocupados. GitHub thu-nmrc/openloop = mesmo conceito (colisão).
- Decisão: **nome = toolloop** (escolha do usuário após ver colisões). **MIT**. Python 3.11+, uv, pytest + provider fake, ruff.
- Flags: renomear pasta `~/Projects/openFlow` → `~/Projects/toolloop` no scaffold.

### Q10 — Escopo final (paralelismo, CLI, subagent)
- Asked: (1) tool calls paralelas? (2) CLI no v1? (3) subagent no core v1?
- Captured: "1. Ok / 2. Ok, no roadmap adicionar um cli básico (init, test, etc) / 3. Sim".
- Decisão: envelope nasce com `"calls": [...]` (lista) mas v1 executa **sequencialmente** (paralelização no roadmap); v1 **library pura** + `examples/` com adapters; **roadmap: CLI básico** (`init`, `test`); `subagent` **no core v1**.

## Open flags (pending input)
- ~~Nome/enum e granularidade dos modos de controle~~ -> **resolvido**: `ControlMode.APPROVE | ControlMode.BYPASS` (2 opções, decisão do usuário na aprovação do plano)
- ~~Renomear pasta~~ -> **executado**: pasta agora é `~/Projects/toolloop` (2026-08-22)
