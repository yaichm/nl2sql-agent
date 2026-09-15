"""SQL generation graph with a repair loop.

Two back-edges turn this pipeline into an agent: a failed validation loops
back to generation, and so does a failed execution. Both are bounded — an
uncapped repair loop is the classic way to burn an API budget on a single
malformed question.

    question -> generate -> validate --+-- ok --> execute --+-- ok --> end
                   ^                  |                    |
                   +----- repair <----+--------------------+
"""

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from nl2sql_agent.agent.baseline import SYSTEM_PROMPT, build_prompt, clean_sql, execute
from nl2sql_agent.providers.base import LLMProvider
from nl2sql_agent.retrieval.selector import SchemaSelector
from nl2sql_agent.retrieval.validate import Catalog, force_limit, validate


class AgentState(TypedDict, total=False):
    question: str
    evidence: str
    schema: str

    sql: str
    rows: list[tuple[Any, ...]] | None

    validation_errors: list[str]
    execution_error: str | None
    blocked: bool

    attempts: int
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    history: list[str]


@dataclass
class AgentResult:
    """Graph output, aligned with Attempt so the two stay interchangeable."""

    question: str
    sql: str
    rows: list[tuple[Any, ...]] | None
    error: str | None
    attempts: int
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    history: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return self.error is None


REPAIR_TEMPLATE = """La requête précédente a échoué.

Requête :
{sql}

Problèmes :
{errors}

Corrige-la. Rends uniquement la requête corrigée."""


def build_graph(
    provider: LLMProvider,
    selector: SchemaSelector,
    catalog: Catalog,
    max_attempts: int = 3,
    row_limit: int = 1000,
) -> Any:
    """Builds the graph. Dependencies are captured via closure."""

    def node_retrieve(state: AgentState) -> AgentState:
        return {
            "schema": selector.select(state["question"]),
            "attempts": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "latency_s": 0.0,
            "history": [],
        }

    def node_generate(state: AgentState) -> AgentState:
        errors = state.get("validation_errors") or []
        exec_error = state.get("execution_error")

        if errors or exec_error:
            # Repair pass: the model gets its own query and the exact error,
            # not just the original question.
            problems = "\n".join(f"- {e}" for e in errors) or f"- {exec_error}"
            user = REPAIR_TEMPLATE.format(sql=state["sql"], errors=problems)
        else:
            user = build_prompt(state["question"], state["schema"], state.get("evidence", ""))

        completion = provider.complete(SYSTEM_PROMPT, user)
        sql = clean_sql(completion.text)

        return {
            "sql": sql,
            "validation_errors": [],
            "execution_error": None,
            "prompt_tokens": state.get("prompt_tokens", 0) + completion.prompt_tokens,
            "completion_tokens": (state.get("completion_tokens", 0) + completion.completion_tokens),
            "latency_s": state.get("latency_s", 0.0) + completion.latency_s,
            "history": [*state.get("history", []), sql],
        }

    def node_validate(state: AgentState) -> AgentState:
        result = validate(state["sql"], catalog)
        return {
            "validation_errors": [str(i) for i in result.issues],
            "blocked": result.blocked,
        }

    def node_execute(state: AgentState) -> AgentState:
        rows, error = execute(force_limit(state["sql"], row_limit), limit=row_limit)
        return {"rows": rows, "execution_error": error}

    def node_repair(state: AgentState) -> AgentState:
        return {"attempts": state.get("attempts", 0) + 1}

    def after_validate(state: AgentState) -> Literal["execute", "repair", "give_up"]:
        if not state.get("validation_errors"):
            return "execute"
        if state.get("blocked"):
            # Security refusal is terminal — we don't ask the model to work
            # around a guardrail.
            return "give_up"
        if state.get("attempts", 0) >= max_attempts:
            return "give_up"
        return "repair"

    def after_execute(state: AgentState) -> Literal["done", "repair", "give_up"]:
        if not state.get("execution_error"):
            return "done"
        if state.get("attempts", 0) >= max_attempts:
            return "give_up"
        return "repair"

    graph = StateGraph(AgentState)
    graph.add_node("retrieve", node_retrieve)
    graph.add_node("generate", node_generate)
    graph.add_node("validate", node_validate)
    graph.add_node("execute", node_execute)
    graph.add_node("repair", node_repair)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "validate")
    graph.add_conditional_edges(
        "validate",
        after_validate,
        {"execute": "execute", "repair": "repair", "give_up": END},
    )
    graph.add_conditional_edges(
        "execute",
        after_execute,
        {"done": END, "repair": "repair", "give_up": END},
    )
    graph.add_edge("repair", "generate")

    return graph.compile()


def answer(
    compiled: Any,
    question: str,
    evidence: str = "",
) -> AgentResult:
    """Runs the graph on a single question."""
    final: AgentState = compiled.invoke(
        {"question": question, "evidence": evidence},
        {"recursion_limit": 50},
    )

    error = final.get("execution_error")
    if not error and final.get("validation_errors"):
        error = "VALIDATION: " + "; ".join(final["validation_errors"])

    return AgentResult(
        question=question,
        sql=final.get("sql", ""),
        rows=final.get("rows"),
        error=error,
        attempts=final.get("attempts", 0),
        prompt_tokens=final.get("prompt_tokens", 0),
        completion_tokens=final.get("completion_tokens", 0),
        latency_s=round(final.get("latency_s", 0.0), 3),
        history=final.get("history", []),
    )
