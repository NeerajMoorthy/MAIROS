/**
 * The orchestrator's agents and the flows that assign them, for the Tasks
 * page's agent map. Mirrors FLOWS in `services/agents/router.py` and the
 * agents' names; tests/test_web_agent_map.py keeps the two in step. Kept
 * static on purpose: the map should explain the system even while the
 * backend is offline.
 */

export interface AgentInfo {
  /** The agent's name in task events and in FLOWS. */
  id: string;
  label: string;
  role: string;
  /** Hue (oklch degrees) for the agent's node and links. */
  hue: number;
}

export const AGENTS: AgentInfo[] = [
  { id: "router", label: "Router", role: "Classifies each request into a flow", hue: 250 },
  { id: "intake", label: "Intake", role: "Reads a project description into a cited brief", hue: 272 },
  { id: "literature", label: "Literature", role: "Searches arXiv, OpenAlex and Semantic Scholar", hue: 295 },
  { id: "indexer", label: "Indexer", role: "Chunks and embeds papers into the vector index", hue: 318 },
  { id: "loader", label: "Loader", role: "Loads an uploaded document's chunks", hue: 340 },
  { id: "retriever", label: "Retriever", role: "Hybrid search: vectors fused with the graph", hue: 2 },
  { id: "analysis", label: "Analysis", role: "Extracts contributions, methods and limitations", hue: 25 },
  { id: "knowledge_graph", label: "Knowledge Graph", role: "Adds papers, authors and concepts to the graph", hue: 48 },
  { id: "comparison", label: "Comparison", role: "Builds a cited comparison table across documents", hue: 70 },
  { id: "gaps", label: "Gaps", role: "Finds research gaps, each quoted from its source", hue: 92 },
  { id: "hypothesis", label: "Hypothesis", role: "Proposes falsifiable hypotheses for evidenced gaps", hue: 115 },
  { id: "novelty", label: "Novelty", role: "Checks ideas against the sources already found", hue: 138 },
  { id: "experiment", label: "Experiment", role: "Turns a hypothesis into a runnable protocol", hue: 160 },
  { id: "patent_awareness", label: "Patent Awareness", role: "Locates project concepts in patent claims", hue: 182 },
  { id: "citation", label: "Citation", role: "Formats sources as APA 7th references", hue: 205 },
  { id: "synthesis", label: "Synthesis", role: "Writes the answer, grounded in retrieved passages", hue: 228 },
];

export interface FlowInfo {
  id: string;
  label: string;
  /** Agents after the Router, in the order the orchestrator runs them. */
  agents: string[];
}

export const FLOWS: FlowInfo[] = [
  { id: "search", label: "Search", agents: ["literature", "indexer", "knowledge_graph", "citation", "synthesis"] },
  { id: "analyze", label: "Analyze upload", agents: ["loader", "analysis", "knowledge_graph", "citation"] },
  { id: "answer", label: "Answer", agents: ["retriever", "synthesis", "citation"] },
  { id: "compare", label: "Compare", agents: ["retriever", "comparison", "citation", "synthesis"] },
  { id: "gaps", label: "Gaps", agents: ["retriever", "gaps", "citation", "synthesis"] },
  {
    id: "hypothesis",
    label: "Hypothesis",
    agents: ["retriever", "gaps", "hypothesis", "novelty", "citation", "synthesis"],
  },
  { id: "novelty", label: "Novelty", agents: ["retriever", "novelty", "citation", "synthesis"] },
  {
    id: "review",
    label: "Literature review",
    agents: [
      "literature", "indexer", "retriever", "comparison", "novelty", "knowledge_graph", "citation", "synthesis",
    ],
  },
  {
    id: "project",
    label: "Project review",
    agents: [
      "intake", "literature", "indexer", "knowledge_graph", "retriever", "comparison", "gaps", "novelty",
      "citation", "synthesis",
    ],
  },
  { id: "patent", label: "Patent", agents: ["retriever", "patent_awareness", "citation", "synthesis"] },
  {
    id: "experiment",
    label: "Experiment",
    agents: ["retriever", "gaps", "hypothesis", "experiment", "citation", "synthesis"],
  },
];

/** Every run starts with the Router choosing the flow. */
export function flowSteps(flow: FlowInfo): string[] {
  return ["router", ...flow.agents];
}

export function agentColor(agent: AgentInfo, alpha = 1): string {
  return `oklch(0.78 0.12 ${agent.hue} / ${alpha})`;
}
