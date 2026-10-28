"""Agent service — multi-agent orchestration for research requests.

Adding a capability (hypothesis generation, novelty detection, experiment
design) is three steps and touches no existing agent:

1. Subclass ``BaseAgent`` and implement ``run(ctx) -> ctx``.
2. Register it in ``AgentOrchestrator.agents``.
3. Name it in a flow in ``router.FLOWS``.
"""

from .analysis import AnalysisAgent
from .base import AgentContext, BaseAgent
from .citations import CitationAgent
from .comparison import ComparisonAgent
from .indexer import IndexerAgent, LoaderAgent, RetrieverAgent
from .intake import ProjectIntakeAgent
from .kg_agent import KnowledgeGraphAgent
from .literature import LiteratureAgent
from .orchestrator import AgentOrchestrator
from .router import FLOWS, RouterAgent, RoutingDecision
from .synthesis import SynthesisAgent

__all__ = [
    "AgentContext",
    "BaseAgent",
    "AgentOrchestrator",
    "RouterAgent",
    "RoutingDecision",
    "FLOWS",
    "LiteratureAgent",
    "AnalysisAgent",
    "CitationAgent",
    "KnowledgeGraphAgent",
    "SynthesisAgent",
    "IndexerAgent",
    "LoaderAgent",
    "RetrieverAgent",
    "ComparisonAgent",
    "ProjectIntakeAgent",
]
