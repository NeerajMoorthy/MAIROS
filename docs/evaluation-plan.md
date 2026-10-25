# Evaluation Plan

## Overview

MAIROS uses a multi-level evaluation strategy that measures quality at both
the component level (retrieval, generation) and the end-to-end system level.

## Evaluation Framework

### RAGAS Metrics

| Metric              | What It Measures                                | Target |
|---------------------|------------------------------------------------|--------|
| Faithfulness        | Are generated claims supported by retrieved context? | ≥ 0.85 |
| Answer Relevancy    | Does the answer address the question?          | ≥ 0.80 |
| Context Precision   | Are retrieved passages relevant to the question? | ≥ 0.75 |
| Context Recall      | Are all necessary passages retrieved?          | ≥ 0.70 |

### Component-Level Evaluation

| Component    | Metric                       | Method                     |
|--------------|------------------------------|----------------------------|
| Chunking     | Chunk coherence score        | LLM-as-judge               |
| Embedding    | Retrieval recall @k          | Golden-set retrieval tests  |
| KG Extraction| Entity/relation F1           | Annotated extraction pairs  |
| Re-ranking   | nDCG@10                      | Relevance judgments         |
| Agent plan   | Sub-task completeness        | Curated multi-hop questions |

## Golden Test Set

### Structure

```json
{
  "id": "q001",
  "question": "How does transformer attention differ from RNN-based attention?",
  "expected_answer": "...",
  "source_documents": ["vaswani2017.pdf", "bahdanau2015.pdf"],
  "required_entities": ["Transformer", "Self-Attention", "RNN"],
  "difficulty": "multi-hop",
  "tags": ["architecture", "attention"]
}
```

### Categories

| Category        | Count | Description                           |
|-----------------|-------|---------------------------------------|
| Single-hop      | 20    | Answered from a single passage        |
| Multi-hop        | 15    | Requires reasoning across 2+ sources  |
| Comparison       | 10    | Compares methods / results            |
| Temporal         | 5     | Requires understanding of timeline    |
| **Total**        | **50**| Initial golden set                    |

## Evaluation Pipeline

```
Golden Set → Query Pipeline → Collect Outputs → Compute RAGAS Metrics → Report
                                    ↓
                            Log: retrieved chunks, KG subgraph,
                            agent reasoning trace, final answer
```

## Ablation Studies

| Experiment                     | Variable                            |
|-------------------------------|-------------------------------------|
| Vector-only vs. Hybrid        | Disable KG retrieval                |
| Fixed vs. Semantic chunking   | Swap chunking strategy              |
| Single-agent vs. Multi-agent  | Bypass Planner, use single LLM call |
| With vs. Without re-ranking   | Disable cross-encoder re-ranker     |

## Reporting

- Generate evaluation reports as Markdown artifacts
- Track metrics over time in a results table
- Include per-question breakdowns for failure analysis
- Visualize metric distributions with plots
