# Versioned Agent Prompts

This package contains versioned system and task prompts for each agent in
the MAIROS multi-agent pipeline.

## Structure

```
prompts/
├── v1/
│   ├── planner.yaml
│   ├── literature.yaml
│   ├── comparison.yaml
│   └── citation.yaml
└── README.md
```

## Versioning Convention

- Each version lives in its own directory (`v1/`, `v2/`, …).
- Prompts are YAML files with `system_prompt` and optional `few_shot_examples`.
- The active version is set via the `PROMPT_VERSION` env var (default: `v1`).
