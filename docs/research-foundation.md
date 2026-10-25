# Research Foundation

## Motivation

Traditional keyword search and single-shot LLM prompting fail on complex
research questions that require synthesizing evidence across multiple documents.
MAIROS addresses this by combining:

1. **Retrieval-Augmented Generation (RAG)** to ground answers in source material
2. **Knowledge Graphs** to capture structured relationships between concepts
3. **Multi-Agent Orchestration** to decompose and reason over complex queries

## Key Research Areas

### 1. Retrieval-Augmented Generation

- Lewis et al., 2020 — *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*
- Gao et al., 2023 — *Retrieval-Augmented Generation for Large Language Models: A Survey*
- Hybrid retrieval (dense + sparse + graph) outperforms single-modality search

### 2. Knowledge Graph Construction

- Pan et al., 2024 — *Unifying Large Language Models and Knowledge Graphs: A Roadmap*
- LLM-based entity and relation extraction enables zero-shot KG construction
- Provenance tracking links every triple to its source chunk

### 3. Multi-Agent Systems

- Wu et al., 2023 — *AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation*
- Park et al., 2023 — *Generative Agents: Interactive Simulacra of Human Behavior*
- Task decomposition + specialist agents improve accuracy on multi-hop questions

### 4. Chunking & Embedding Strategies

- Semantic chunking preserves context better than fixed-size windows
- Late-interaction models (ColBERT) improve retrieval precision
- Embedding model choice significantly impacts downstream answer quality

### 5. Evaluation

- Es et al., 2023 — *RAGAS: Automated Evaluation of Retrieval Augmented Generation*
- Component-level evaluation (retrieval, generation, faithfulness) is critical
- Human-in-the-loop evaluation for nuanced research quality assessment

## Hypotheses

| # | Hypothesis | Metric |
|---|-----------|--------|
| H1 | Hybrid retrieval (vector + KG) improves context precision over vector-only | Context Precision (RAGAS) |
| H2 | Multi-agent decomposition improves answer completeness on multi-hop questions | Answer Relevancy (RAGAS) |
| H3 | Citation grounding reduces hallucination rate | Faithfulness (RAGAS) |
| H4 | Semantic chunking outperforms fixed-size chunking | Retrieval Recall |

## Design Principles

1. **Evidence-first**: Every generated claim must be traceable to a source
2. **Composable**: Services can be used independently or in concert
3. **Evaluable**: Every pipeline stage has measurable quality metrics
4. **Iterative**: The system supports incremental knowledge accumulation
