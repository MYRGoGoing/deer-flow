import json
from types import SimpleNamespace

import pytest

from deerflow.community.kb_search.config import EvaluationConfig
from deerflow.community.kb_search.evaluation import (
    OpenAICompatibleChatBackend,
    aggregate_e2e_metrics,
    evaluate_answer,
    generate_answer,
    get_evaluation_chat_backend,
    is_refusal,
    judge_answer,
    token_f1,
)


class FakeCompletions:
    def __init__(self, content: str | list[str | None]) -> None:
        self.contents = iter(content if isinstance(content, list) else [content])
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=next(self.contents)))])


class FakeBackend:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls = []

    def complete(self, system: str, user: str, *, model: str | None = None) -> str:
        self.calls.append((system, user, model))
        return next(self.responses)


def _hits() -> list[dict]:
    return [
        {
            "doc_title": "架构说明",
            "section_path": "节点类型",
            "source_file": "platform/architecture.md",
            "source": "",
            "text": "VP 是共识节点，NVP 不参与共识。",
            "weak_evidence": False,
        }
    ]


def test_openai_compatible_chat_backend_uses_zero_temperature():
    completions = FakeCompletions("answer [1]")
    backend = OpenAICompatibleChatBackend(
        EvaluationConfig(model="chat-model"),
        "secret",
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )

    assert backend.complete("system", "user") == "answer [1]"
    assert completions.calls[0]["temperature"] == 0
    assert completions.calls[0]["model"] == "chat-model"


def test_openai_compatible_chat_backend_retries_empty_content(monkeypatch):
    monkeypatch.setattr("deerflow.community.kb_search.evaluation.time.sleep", lambda _delay: None)
    completions = FakeCompletions([None, "answer [1]"])
    backend = OpenAICompatibleChatBackend(
        EvaluationConfig(model="chat-model", max_retries=1),
        "secret",
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )

    assert backend.complete("system", "user") == "answer [1]"
    assert len(completions.calls) == 2


def test_openai_compatible_chat_backend_retries_unclosed_code_fence(monkeypatch):
    monkeypatch.setattr("deerflow.community.kb_search.evaluation.time.sleep", lambda _delay: None)
    completions = FakeCompletions(["example [1]\n```java\npublic void", "use @Transaction [1]"])
    backend = OpenAICompatibleChatBackend(
        EvaluationConfig(model="chat-model", max_retries=1),
        "secret",
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )

    assert backend.complete("system", "user") == "use @Transaction [1]"
    assert len(completions.calls) == 2


def test_generate_answer_short_circuits_when_all_evidence_is_weak():
    backend = FakeBackend(["should not be used"])
    weak_hits = [{**_hits()[0], "weak_evidence": True}]

    answer = generate_answer("VP 是什么？", weak_hits, backend)

    assert "知识库中暂无相关内容" in answer
    assert backend.calls == []


def test_refusal_detection_keeps_cited_partial_answer():
    answer = "字节码和 ABI 可直接部署。[2] 资料未提供更详细步骤，无法基于现有资料补充。"

    assert not is_refusal(answer)
    assert is_refusal("知识库中暂无相关内容，无法基于现有资料给出可靠回答。")


def test_evaluate_answer_checks_keywords_citations_and_source():
    item = {
        "answer": "VP 是共识节点，NVP 不参与共识。",
        "source": "platform/architecture.md",
        "keywords": ["VP", "NVP", "共识"],
    }

    metrics = evaluate_answer(
        item,
        "VP 参与共识，NVP 不参与共识。[1][3]",
        _hits(),
    )

    assert metrics["keyword_recall"] == 1.0
    assert metrics["citation_validity"] == 0.5
    assert metrics["expected_source_cited"] is True
    assert metrics["refusal_correct"] is True
    assert token_f1(item["answer"], item["answer"]) == 1.0


def test_judge_answer_parses_json_from_fenced_response():
    payload = {"faithfulness": 0.9, "answer_relevancy": 0.8, "reason": "supported"}
    backend = FakeBackend([f"```json\n{json.dumps(payload)}\n```"])

    result = judge_answer("question", "answer [1]", _hits(), backend, model="judge")

    assert result["faithfulness"] == 0.9
    assert backend.calls[0][2] == "judge"


def test_get_evaluation_chat_backend_requires_model_and_key(monkeypatch):
    for name in ("KB_E2E_API_KEY", "SILICONFLOW_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="KB_E2E_MODEL"):
        get_evaluation_chat_backend(EvaluationConfig())
    with pytest.raises(RuntimeError, match="KB_E2E_API_KEY"):
        get_evaluation_chat_backend(EvaluationConfig(model="chat-model"))


def test_aggregate_e2e_metrics_separates_answerable_and_judged_cases():
    cases = [
        {
            "unanswerable": False,
            "metrics": {
                "refusal_correct": True,
                "keyword_recall": 1.0,
                "answer_token_f1": 0.8,
                "citation_validity": 1.0,
                "expected_source_cited": True,
            },
            "judge": {"faithfulness": 0.9, "answer_relevancy": 0.8},
        },
        {
            "unanswerable": True,
            "metrics": {
                "refusal_correct": True,
                "keyword_recall": None,
                "answer_token_f1": None,
                "citation_validity": 0.0,
                "expected_source_cited": None,
            },
            "judge": None,
        },
    ]

    result = aggregate_e2e_metrics(cases)

    assert result["case_count"] == 2
    assert result["refusal_accuracy"] == 1.0
    assert result["keyword_recall"] == 1.0
    assert result["judged_count"] == 1
