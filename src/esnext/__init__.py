"""Current LightScientist control structure prototype."""

from .executor import ExecutionRuntime
from .manager import StageManager
from .minimal_agent import run_agent
from .data_models import AgentRecord, AgentRunResult, ExecutionResult, RuntimeTask, StageRequest
from .research_controller import ResearchController
from .runtime import RuntimeSupervisor

__all__ = [
    "AgentRecord",
    "AgentRunResult",
    "ExecutionRuntime",
    "ExecutionResult",
    "RuntimeSupervisor",
    "RuntimeTask",
    "ResearchController",
    "StageManager",
    "StageRequest",
    "run_agent",
]
