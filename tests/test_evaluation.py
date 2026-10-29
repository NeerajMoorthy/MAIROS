"""Evaluation harness tests — fully offline and deterministic.

The metric assertions use hand-worked examples rather than golden files: if
the arithmetic drifts, these fail with a number a human can check on paper.
"""

from __future__ import annotations

from math import log2

import pytest

# Aliased: pytest would otherwise try to collect the `TestCase` dataclass.
from services.evaluation.golden_set import GoldenSet, normalise
from services.evaluation.golden_set import TestCase as GoldenCase
from services.evaluation.metrics import (
    aggregate,
    dcg_at_k,
    evaluate_ranking,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from services.evaluation.runner import RetrievalEvaluator


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
class TestMetrics:
    RANKED = ["c1", "c2", "c3", "c4", "c5"]

    def test_recall_counts_only_relevant_in_top_k(self):
        # 2 of the 4 relevant chunks are inside the top 5.
        assert recall_at_k(self.RANKED, {"c2", "c4", "c9", "c10"}, 5) == 0.5

    def test_recall_is_zero_when_nothing_relevant_exists(self):
        assert recall_at_k(self.RANKED, set(), 5) == 0.0

    def test_precision_divides_by_k_not_by_results_returned(self):
        # Only two results returned, one relevant: P@5 is 1/5, not 1/2.
        assert precision_at_k(["c1", "c2"], {"c1"}, 5) == pytest.approx(0.2)

    def test_reciprocal_rank_uses_the_first_relevant_position(self):
        assert reciprocal_rank(self.RANKED, {"c3", "c5"}) == pytest.approx(1 / 3)
        assert reciprocal_rank(self.RANKED, {"c1"}) == 1.0
        assert reciprocal_rank(self.RANKED, {"missing"}) == 0.0

    def test_dcg_applies_log2_discounting(self):
        # Relevant at ranks 1 and 3 -> 1/log2(2) + 1/log2(4) = 1.0 + 0.5
        assert dcg_at_k(self.RANKED, {"c1", "c3"}, 5) == pytest.approx(1.5)

    def test_ndcg_is_one_for_a_perfect_ranking(self):
        assert ndcg_at_k(self.RANKED, {"c1", "c2"}, 5) == pytest.approx(1.0)

    def test_ndcg_penalises_a_late_relevant_hit(self):
        # Single relevant item at rank 3: DCG = 1/log2(4) = 0.5, IDCG = 1.0
        assert ndcg_at_k(self.RANKED, {"c3"}, 5) == pytest.approx(0.5)

    def test_ndcg_normalises_against_the_achievable_ideal(self):
        # 3 relevant exist but k=2, so the ideal only counts the first two.
        ideal = 1.0 + 1.0 / log2(3)
        expected = (1.0 / log2(3)) / ideal  # only "c2" is inside the top 2
        assert ndcg_at_k(self.RANKED, {"c2", "c8", "c9"}, 2) == pytest.approx(
            expected, abs=1e-4
        )

    def test_evaluate_ranking_reports_all_four_metrics(self):
        result = evaluate_ranking(self.RANKED, {"c2"}, k=5)
        assert result == {
            "recall_at_5": 1.0,
            "precision_at_5": 0.2,
            "reciprocal_rank": 0.5,
            "ndcg_at_5": pytest.approx(0.6309, abs=1e-4),
        }

    def test_aggregate_averages_and_renames_rr_to_mrr(self):
        agg = aggregate(
            [
                {"recall_at_5": 1.0, "precision_at_5": 0.2, "reciprocal_rank": 1.0, "ndcg_at_5": 1.0},
                {"recall_at_5": 0.0, "precision_at_5": 0.0, "reciprocal_rank": 0.0, "ndcg_at_5": 0.0},
            ],
            k=5,
        )
        assert agg["recall_at_5"] == 0.5
        assert agg["mrr"] == 0.5
        assert agg["cases_evaluated"] == 2

    def test_aggregate_of_nothing_is_unmeasured_not_zero(self):
        """Regression (walkthrough K3): with no case to average, the metrics were
        0.0, which the dashboard printed as a measured 0.000."""
        agg = aggregate([], k=5)

        assert agg["cases_evaluated"] == 0
        for name in ("recall_at_5", "precision_at_5", "mrr", "ndcg_at_5"):
            assert agg[name] is None


# ---------------------------------------------------------------------------
# Golden set and its relevance rule
# ---------------------------------------------------------------------------
class TestGoldenSet:
    def test_shipped_set_loads_and_is_curated(self):
        golden = GoldenSet()
        assert len(golden) >= 8
        assert golden.metadata.get("relevance_policy") == "term_match"
        assert all(case.question and case.id for case in golden)
        assert all(
            case.required_entities or case.source_documents for case in golden
        ), "every case must declare how relevance is judged"

    def test_ids_are_unique(self):
        ids = [case.id for case in GoldenSet()]
        assert len(ids) == len(set(ids))

    def test_normalise_collapses_punctuation_and_case(self):
        assert normalise("Self-Attention!") == normalise("self   attention")

    def test_term_match_requires_every_term(self):
        case = GoldenCase(
            id="t", question="q", required_entities=["retrieval", "hallucination"]
        )
        assert case.is_relevant({"text": "Retrieval reduces hallucination rates."})
        assert not case.is_relevant({"text": "Retrieval improves latency."})

    def test_hyphenation_does_not_decide_relevance(self):
        case = GoldenCase(id="t", question="q", required_entities=["self attention"])
        assert case.is_relevant({"text": "The Self-Attention block scores tokens."})

    def test_document_labels_take_priority_over_terms(self):
        case = GoldenCase(
            id="t",
            question="q",
            source_documents=["attention is all you need"],
            required_entities=["nonexistent term"],
        )
        assert case.is_relevant({"document_name": "Attention Is All You Need.pdf", "text": ""})
        assert not case.is_relevant({"document_name": "Other Paper.pdf", "text": ""})
        assert case.policy == "document_label"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def _corpus() -> list[dict]:
    return [
        {"chunk_id": "a1", "text": "Retrieval grounds answers and reduces hallucination.", "document_name": "rag.pdf"},
        {"chunk_id": "a2", "text": "Hallucination drops when retrieval supplies evidence.", "document_name": "rag.pdf"},
        {"chunk_id": "b1", "text": "Self attention processes a sequence in parallel.", "document_name": "tf.pdf"},
        {"chunk_id": "z1", "text": "Unrelated boilerplate about formatting.", "document_name": "misc.pdf"},
    ]


class TestRetrievalEvaluator:
    def _golden(self, tmp_path) -> GoldenSet:
        import json

        path = tmp_path / "golden.json"
        path.write_text(
            json.dumps(
                {
                    "relevance_policy": "term_match",
                    "test_cases": [
                        {
                            "id": "supported",
                            "question": "does retrieval reduce hallucination?",
                            "required_entities": ["retrieval", "hallucination"],
                        },
                        {
                            "id": "unsupported",
                            "question": "what about quantum annealing schedules?",
                            "required_entities": ["quantum annealing"],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        return GoldenSet(path)

    def test_perfect_retriever_scores_one(self, tmp_path):
        def retrieve(question, k):
            return [c for c in _corpus() if c["chunk_id"] in {"a1", "a2"}][:k]

        report = RetrievalEvaluator(retrieve, _corpus, self._golden(tmp_path), k=5).run()

        supported = [c for c in report.cases if c.supported]
        assert len(supported) == 1
        assert supported[0].relevant_in_corpus == 2
        assert report.aggregates["recall_at_5"] == 1.0
        assert report.aggregates["mrr"] == 1.0
        assert report.aggregates["ndcg_at_5"] == 1.0

    def test_bad_ranking_is_penalised_but_still_recalled(self, tmp_path):
        def retrieve(question, k):
            order = {"z1": 0, "b1": 1, "a1": 2, "a2": 3}
            return sorted(_corpus(), key=lambda c: order.get(c["chunk_id"], 9))[:k]

        report = RetrievalEvaluator(retrieve, _corpus, self._golden(tmp_path), k=5).run()
        metrics = [c.metrics for c in report.cases if c.supported][0]

        assert metrics["recall_at_5"] == 1.0  # both relevant chunks retrieved
        # Reported metrics are rounded to 4 dp, hence the tolerance.
        assert metrics["reciprocal_rank"] == pytest.approx(1 / 3, abs=1e-4)  # rank 3
        assert metrics["ndcg_at_5"] < 1.0

    def test_case_with_no_relevant_passage_is_unsupported_not_zero(self, tmp_path):
        report = RetrievalEvaluator(
            lambda q, k: _corpus()[:k], _corpus, self._golden(tmp_path), k=5
        ).run()

        unsupported = [c for c in report.cases if not c.supported]
        assert [c.id for c in unsupported] == ["unsupported"]
        assert unsupported[0].metrics == {}
        assert "Excluded from the aggregates" in unsupported[0].note
        assert report.to_dict()["cases_unsupported"] == 1
        # The unsupported case must not drag the average down.
        assert report.aggregates["cases_evaluated"] == 1

    def test_report_is_transparent_about_ragas(self, tmp_path):
        report = RetrievalEvaluator(
            lambda q, k: [], _corpus, self._golden(tmp_path), k=5
        ).run()

        assert report.ragas["scores"] is None
        assert isinstance(report.ragas["available"], bool)
        assert report.ragas["kind"] == "model_judged"
        assert report.ragas["reason"]
        assert report.ragas["metrics"] == [
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
        ]

    def test_empty_retrieval_scores_zero_without_crashing(self, tmp_path):
        report = RetrievalEvaluator(
            lambda q, k: [], _corpus, self._golden(tmp_path), k=5
        ).run()
        assert report.aggregates["recall_at_5"] == 0.0
        assert report.aggregates["mrr"] == 0.0

    def test_a_corpus_no_case_applies_to_reports_no_metric(self, tmp_path):
        """Regression (walkthrough K3). The opposite of the test above: here no
        case has evidence in the corpus at all, so the retriever was never
        measured. The railway sample project is such a corpus, and its
        dashboard showed 0.000 for every metric."""

        def railway():
            return [{"chunk_id": "r1", "text": "Camera inspection of rail heads.", "document_name": "rail.pdf"}]

        report = RetrievalEvaluator(lambda q, k: [], railway, self._golden(tmp_path), k=5).run()

        assert report.supported_cases == []
        for name in ("recall_at_5", "precision_at_5", "mrr", "ndcg_at_5"):
            assert report.aggregates[name] is None


# ---------------------------------------------------------------------------
# Answer-quality (RAGAS) scoring
# ---------------------------------------------------------------------------
class TestAnswerQuality:
    def test_missing_ragas_is_reported_not_scored(self, monkeypatch):
        from services.evaluation import ragas_runner

        monkeypatch.setattr(ragas_runner, "ragas_installed", lambda: False)
        monkeypatch.setattr(ragas_runner, "llm_is_live", lambda: True)

        report = ragas_runner.unavailable_report()
        assert report.available is False
        assert report.scores is None
        assert report.reason == "ragas_not_installed"
        assert "not installed" in report.note

    def test_missing_live_model_is_reported_not_scored(self, monkeypatch):
        from services.evaluation import ragas_runner

        monkeypatch.setattr(ragas_runner, "ragas_installed", lambda: True)
        monkeypatch.setattr(ragas_runner, "llm_is_live", lambda: False)

        report = ragas_runner.unavailable_report()
        assert report.available is False
        assert report.reason == "no_live_llm"
        assert "live LLM" in report.note

    def test_both_conditions_must_hold(self, monkeypatch):
        from services.evaluation import ragas_runner

        monkeypatch.setattr(ragas_runner, "ragas_installed", lambda: True)
        monkeypatch.setattr(ragas_runner, "llm_is_live", lambda: True)
        assert ragas_runner.unavailable_report().available is True

    def test_offline_environment_never_produces_a_score(self):
        """The suite runs with no key and no ragas — this is the real state."""
        from services.evaluation.ragas_runner import score_samples

        report = score_samples([{"question": "q", "answer": "a", "contexts": ["c"], "ground_truth": "g"}])
        assert report.available is False
        assert report.scores is None

    def test_build_samples_uses_the_real_answer_path(self):
        from services.evaluation.golden_set import GoldenSet
        from services.evaluation.ragas_runner import build_samples

        seen: list[str] = []

        def answer_fn(question: str):
            seen.append(question)
            return f"answer to {question}", ["ctx1", "ctx2"]

        samples = build_samples(list(GoldenSet())[:2], answer_fn)

        assert len(samples) == 2
        assert len(seen) == 2
        assert samples[0]["contexts"] == ["ctx1", "ctx2"]
        assert samples[0]["ground_truth"], "the expected answer is the ground truth"

    def test_empty_sample_set_is_reported_not_scored(self, monkeypatch):
        from services.evaluation import ragas_runner

        monkeypatch.setattr(ragas_runner, "ragas_installed", lambda: True)
        monkeypatch.setattr(ragas_runner, "llm_is_live", lambda: True)

        report = ragas_runner.score_samples([])
        assert report.available is False
        assert report.reason == "no_samples"

    def test_runner_explains_when_answer_generation_was_not_requested(
        self, tmp_path, monkeypatch
    ):
        from services.evaluation import ragas_runner

        monkeypatch.setattr(ragas_runner, "ragas_installed", lambda: True)
        monkeypatch.setattr(ragas_runner, "llm_is_live", lambda: True)

        import json

        path = tmp_path / "golden.json"
        path.write_text(
            json.dumps({"test_cases": [{"id": "a", "question": "q", "required_entities": ["x"]}]}),
            encoding="utf-8",
        )

        report = RetrievalEvaluator(
            lambda q, k: [], _corpus, GoldenSet(path), k=5, answer_fn=None
        ).run()

        assert report.ragas["available"] is False
        assert report.ragas["reason"] == "no_answer_function"


# ---------------------------------------------------------------------------
# RAGAS judging with MAIROS's own model and embedder
# ---------------------------------------------------------------------------
class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def to_pandas(self):
        rows = self._rows

        class _Frame:
            def to_dict(self, orient):
                assert orient == "records"
                return rows

        return _Frame()


@pytest.fixture()
def fake_ragas(monkeypatch):
    """A stand-in ``ragas`` that records what evaluate() was given."""
    import sys
    import types

    from services.evaluation import ragas_runner

    monkeypatch.setattr(ragas_runner, "ragas_installed", lambda: True)
    monkeypatch.setattr(ragas_runner, "llm_is_live", lambda: True)

    calls: dict = {"rows": []}

    def evaluate(dataset, metrics=None, llm=None, embeddings=None, run_config=None, **kwargs):
        calls.update(dataset=dataset, metrics=metrics, llm=llm, embeddings=embeddings, run_config=run_config)
        return _FakeResult(calls["rows"])

    module = types.ModuleType("ragas")
    module.evaluate = evaluate
    module.RunConfig = lambda **kwargs: kwargs
    module.EvaluationDataset = types.SimpleNamespace(from_list=lambda rows: rows)
    metrics = types.ModuleType("ragas.metrics")
    for name in ragas_runner.METRIC_NAMES:
        setattr(metrics, name, name)
    monkeypatch.setitem(sys.modules, "ragas", module)
    monkeypatch.setitem(sys.modules, "ragas.metrics", metrics)
    return calls


def _sample(question, answer="an answer", contexts=("a passage",)):
    return {"question": question, "answer": answer, "contexts": list(contexts), "ground_truth": "truth"}


class TestRagasJudge:
    def test_judges_with_the_given_model_and_the_local_embedder(self, fake_ragas):
        """Left to itself RAGAS judges with OpenAI, which MAIROS has no key for,
        so every run failed even with ragas installed."""
        from services.evaluation.ragas_runner import score_samples

        judge = object()
        fake_ragas["rows"] = [{m: 0.5 for m in ("faithfulness", "answer_relevancy", "context_precision", "context_recall")}]

        report = score_samples([_sample("q1")], llm=judge, embeddings=lambda texts: [[1, 2]] * len(texts))

        assert report.available is True
        assert fake_ragas["llm"] is judge
        assert fake_ragas["embeddings"].embed_query("hello") == [1.0, 2.0]
        assert fake_ragas["embeddings"].embed_documents(["a", "b"]) == [[1.0, 2.0], [1.0, 2.0]]
        assert fake_ragas["run_config"]["max_workers"] <= 4, "stay inside Groq's request rate"
        assert fake_ragas["dataset"] == [
            {"user_input": "q1", "response": "an answer", "retrieved_contexts": ["a passage"], "reference": "truth"}
        ]

    def test_scores_are_the_mean_of_the_judgements_that_succeeded(self, fake_ragas):
        """RAGAS returns its results as a table, with NaN for a failed
        judgement. The old code read them with .get(), which RAGAS's result has
        not got, so even a good run reported no scores."""
        from services.evaluation.ragas_runner import score_samples

        nan = float("nan")
        fake_ragas["rows"] = [
            {"faithfulness": 1.0, "answer_relevancy": 0.8, "context_precision": nan, "context_recall": 0.5},
            {"faithfulness": 0.5, "answer_relevancy": nan, "context_precision": nan, "context_recall": 1.0},
        ]

        report = score_samples([_sample("q1"), _sample("q2")], llm=object(), embeddings=lambda t: [[0.0]] * len(t))

        assert report.scores == {"faithfulness": 0.75, "answer_relevancy": 0.8, "context_recall": 0.75}
        assert [case["question"] for case in report.per_case] == ["q1", "q2"]
        assert report.per_case[1]["answer_relevancy"] is None
        assert report.judged_by is not None

    def test_cases_without_passages_are_skipped_not_judged(self, fake_ragas):
        from services.evaluation.ragas_runner import score_samples

        fake_ragas["rows"] = [{"faithfulness": 1.0}]
        samples = [_sample("q1"), _sample("q2", answer="", contexts=()), _sample("q3", contexts=())]

        report = score_samples(samples, llm=object(), embeddings=lambda t: [[0.0]] * len(t))

        assert [row["user_input"] for row in fake_ragas["dataset"]] == ["q1"]
        assert "2 skipped" in report.note

    def test_nothing_to_judge_is_reported(self, fake_ragas):
        from services.evaluation.ragas_runner import score_samples

        report = score_samples([_sample("q1", answer="", contexts=())], llm=object())
        assert report.available is False
        assert report.reason == "no_samples"
        assert "dataset" not in fake_ragas, "ragas must not be called with nothing to judge"

    def test_every_judgement_failing_shows_no_score(self, fake_ragas):
        from services.evaluation.ragas_runner import score_samples

        nan = float("nan")
        fake_ragas["rows"] = [{name: nan for name in ("faithfulness", "answer_relevancy")}]

        report = score_samples([_sample("q1")], llm=object(), embeddings=lambda t: [[0.0]] * len(t))
        assert report.available is False
        assert report.scores is None
        assert report.reason == "no_scores_returned"

    def test_the_real_ragas_accepts_the_judge_without_openai(self, monkeypatch):
        """Runs only where ragas is installed (CI installs the requirements).
        A judge that always errors must end in "no scores", not in RAGAS
        asking for an OpenAI key."""
        pytest.importorskip("ragas")
        from langchain_core.language_models.fake_chat_models import FakeListChatModel

        from services.evaluation import ragas_runner

        monkeypatch.setattr(ragas_runner, "llm_is_live", lambda: True)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        class BrokenJudge(FakeListChatModel):
            def _call(self, *args, **kwargs):
                raise RuntimeError("judge unavailable")

        report = ragas_runner.score_samples(
            [_sample("What is retrieval-augmented generation?")],
            llm=BrokenJudge(responses=["unused"]),
            embeddings=lambda texts: [[0.1, 0.2, 0.3]] * len(texts),
        )

        assert report.available is False
        assert report.reason == "no_scores_returned", report.note


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
class TestEvaluationAPI:
    def test_status_reports_what_is_measurable(self, client):
        status = client.get("/api/evaluation/status").json()
        assert status["status"] == "ready"
        assert status["retrieval_metrics_available"] is True
        assert status["golden_set_size"] >= 8
        # Answer metrics are only claimed when RAGAS is genuinely importable
        # and there is a live model to judge with.
        assert status["answer_metrics_available"] == (status["ragas_installed"] and status["llm_live"])

    def test_golden_set_endpoint_exposes_the_cases(self, client):
        payload = client.get("/api/evaluation/golden-set").json()
        assert payload["size"] == len(payload["cases"])
        assert all(case["policy"] in {"term_match", "document_label"} for case in payload["cases"])

    def test_run_scores_a_real_project(self, client, sample_pdf):
        project_id = client.post("/api/projects", json={"name": "Eval"}).json()["id"]
        with open(sample_pdf, "rb") as handle:
            upload = client.post(
                f"/api/projects/{project_id}/documents",
                files={"file": ("paper.pdf", handle, "application/pdf")},
            )
        assert upload.status_code == 201

        report = client.post(
            f"/api/projects/{project_id}/evaluation/run", json={"k": 5}
        ).json()

        assert report["k"] == 5
        assert report["corpus_chunks"] > 0
        assert report["cases_total"] >= 8
        # The sample PDF covers self-attention and RAG, so at least one curated
        # case must be evaluable against it.
        assert report["cases_evaluated"] >= 1
        assert 0.0 <= report["aggregates"]["recall_at_5"] <= 1.0
        assert 0.0 <= report["aggregates"]["mrr"] <= 1.0
        assert report["ragas"]["scores"] is None

        evaluated = [case for case in report["cases"] if case["supported"]]
        assert all(case["relevant_in_corpus"] > 0 for case in evaluated)

    def test_run_rejects_an_unknown_project(self, client):
        assert client.post("/api/projects/nope/evaluation/run", json={"k": 5}).status_code == 404
