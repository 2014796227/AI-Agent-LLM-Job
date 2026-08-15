import time
from dataclasses import dataclass, field
from app.config import settings

class BudgetExceeded(Exception):
    def __init__(self, reason: str):
        self.reason = reason

@dataclass
class TaskBudget:
    max_dag_nodes: int = settings.budget_max_dag_nodes
    max_llm_calls: int = settings.budget_max_llm_calls
    max_tool_calls: int = settings.budget_max_tool_calls
    max_tokens: int = settings.budget_max_tokens
    deadline: float = field(
        default_factory=lambda: time.monotonic() + settings.budget_wall_clock_s)
    llm_calls: int = 0
    tool_calls: int = 0
    tokens: int = 0

    def _check_time(self):
        if time.monotonic() > self.deadline:
            raise BudgetExceeded("wall_clock")

    def check_llm(self):
        self._check_time()
        if self.llm_calls >= self.max_llm_calls:
            raise BudgetExceeded(f"llm_calls≥{self.max_llm_calls}")
        if self.tokens >= self.max_tokens:
            raise BudgetExceeded(f"tokens≥{self.max_tokens}")

    def spend_llm(self, tokens: int):
        self.llm_calls += 1
        self.tokens += tokens

    def final_check(self):
        """末次调用后超支也判降级（调用后累计、再无检查点的漏洞封堵）。"""
        self._check_time()
        if self.llm_calls > self.max_llm_calls or self.tokens > self.max_tokens:
            raise BudgetExceeded("overspend_on_final")

    def check_tool(self):
        self._check_time()
        if self.tool_calls >= self.max_tool_calls:
            raise BudgetExceeded(f"tool_calls≥{self.max_tool_calls}")

    def spend_tool(self):
        self.tool_calls += 1
