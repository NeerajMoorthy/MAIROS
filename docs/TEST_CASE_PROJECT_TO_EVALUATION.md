# End-to-end test case: project to evaluation

**ID:** E2E-01  
**Purpose:** Verify that a researcher can create a project, upload a controlled corpus, inspect the agent run, and evaluate retrieval quality.

## Preconditions

- The API and web app are running.
- The API and web app can write to their configured local data directories.
- A configured LLM is needed for the background document-analysis agents. Upload ingestion and retrieval evaluation do not depend on those agents completing successfully.

## Test data

| Field | Value |
| --- | --- |
| Project name | `RAG evaluation smoke test` |
| Description | `End-to-end retrieval and evaluation check` |
| Upload file | [`e2e-rag-evaluation-source.pdf`](../output/pdf/e2e-rag-evaluation-source.pdf) |
| Full structured data | [`e2e-rag-evaluation-data.json`](fixtures/e2e-rag-evaluation-data.json) |

## Steps and expected results

1. Open **Projects** and select **New Project**.
2. Enter the project name and description above, then select **Create project**.
   - A workspace opens for `RAG evaluation smoke test`.
3. In **Search & Upload**, upload `e2e-rag-evaluation-source.pdf`.
   - The upload reports 10 pages and at least 10 indexed chunks. An analysis workflow starts.
4. Open **Agent Activity** and wait until the workflow becomes **completed** or **failed**.
   - The trace shows Loader → Analysis → Knowledge Graph → Citation. If the model provider is rate limited, the task error remains readable and the uploaded, indexed document stays available.
5. Return to **Search & Upload**.
   - One uploaded document and at least 10 indexed chunks are present. The project does not need retrieved arXiv papers for this case.
6. Open **Evaluation** from the sidebar, select `RAG evaluation smoke test`, then select **Run evaluation**.
   - The report shows Recall@5, Precision@5, MRR, and nDCG@5, each between 0 and 1.
   - All 10 cases are supported because the fixture contains every required term pair.
   - This retrieval-only run does not display answer-quality scores because it does not provide generated answers to a judge.
7. Return to **Projects**, use the trash button on the test project, and confirm **Delete project**.
   - The project disappears from the list. Its uploaded files, indexed chunks, graph, papers, and task history are removed.

## Pass criteria

The project is created, a corpus is indexed, the task history remains readable at desktop and mobile widths, evaluation produces an evidence-scoped report, and the project can be deleted with confirmation.
