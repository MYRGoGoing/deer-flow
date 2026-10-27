"""End-to-end RAG generation and evaluation helpers."""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from statistics import mean
from typing import Any

from .config import EvaluationConfig, load_kb_config
from .retriever import format_results
from .stores import tokenize

REFUSAL_TEXT = "知识库中暂无相关内容，无法基于现有资料给出可靠回答。"
REFUSAL_MARKERS = ("知识库中暂无相关内容", "无法基于现有资料", "证据不足")


class ChatBackend:
    name: str = "base"

    def complete(self, system: str, user: str, *, model: str | None = None) -> str:
        raise NotImplementedError


class OpenAICompatibleChatBackend(ChatBackend):
    def __init__(
        self,
        config: EvaluationConfig,
        api_key: str,
        *,
        client: Any | None = None,
    ) -> None:
        self.config = config
        self.name = f"openai:{config.model}"
        if client is None:
            from openai import OpenAI

            client = OpenAI(
                base_url=config.base_url,
                api_key=api_key,
                timeout=config.timeout_seconds,
                max_retries=config.max_retries,
            )
        self.client = client

    def complete(self, system: str, user: str, *, model: str | None = None) -> str:
        attempts = self.config.max_retries + 1
        for attempt in range(attempts):
            response = self.client.chat.completions.create(
                model=model or self.config.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                max_tokens=self.config.max_tokens,
            )
            content = response.choices[0].message.content
            if isinstance(content, str) and content.strip():
                normalized = content.strip()
                if normalized.count("```") % 2 == 0:
                    return normalized
            if attempt + 1 < attempts:
                time.sleep(min(2**attempt, 4))
        raise RuntimeError(f"Evaluation chat model returned empty or incomplete content after {attempts} attempts")


def get_evaluation_chat_backend(
    config: EvaluationConfig | None = None,
) -> ChatBackend:
    config = config or load_kb_config().evaluation
    if not config.model:
        raise RuntimeError("End-to-end evaluation requires KB_E2E_MODEL")
    api_key = os.environ.get("KB_E2E_API_KEY") or os.environ.get("SILICONFLOW_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("End-to-end evaluation requires KB_E2E_API_KEY")
    return OpenAICompatibleChatBackend(config, api_key)


def generate_answer(question: str, hits: list[dict], backend: ChatBackend) -> str:
    if not hits or all(hit.get("weak_evidence", False) for hit in hits):
        return REFUSAL_TEXT
    system = f"你是企业知识库问答助手。只能使用用户提供的检索证据回答，不得使用模型记忆补充事实。每个事实性结论必须标注对应证据编号，如[1]；证据不足时只回答：{REFUSAL_TEXT}"
    user = f"问题：{question}\n\n检索证据：\n{format_results(hits)}"
    return backend.complete(system, user)


def extract_citations(answer: str) -> list[int]:
    return [int(value) for value in re.findall(r"\[(\d+)]", answer)]


def is_refusal(answer: str) -> bool:
    normalized = answer.strip()
    if normalized == REFUSAL_TEXT:
        return True
    # A supported answer may end with a scoped caveat such as "the documents do
    # not provide more detailed steps". Treat it as a refusal only when the
    # response contains no citation-backed answer and is itself short.
    return not extract_citations(normalized) and len(normalized) <= len(REFUSAL_TEXT) * 2 and any(marker in normalized for marker in REFUSAL_MARKERS)


def token_f1(expected: str, actual: str) -> float:
    expected_tokens = tokenize(expected)
    actual_tokens = tokenize(actual)
    if not expected_tokens or not actual_tokens:
        return 0.0
    overlap = sum((Counter(expected_tokens) & Counter(actual_tokens)).values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(actual_tokens)
    recall = overlap / len(expected_tokens)
    return 2 * precision * recall / (precision + recall)


def evaluate_answer(item: dict, answer: str, hits: list[dict]) -> dict:
    unanswerable = bool(item.get("unanswerable"))
    refused = is_refusal(answer)
    citations = extract_citations(answer)
    unique_citations = sorted(set(citations))
    valid_citations = [number for number in unique_citations if 1 <= number <= len(hits)]
    source = item.get("source")
    source_cited = any(hits[number - 1].get("source_file") == source for number in valid_citations if source)
    keywords = item.get("keywords", [])
    keyword_hits = sum(keyword.lower() in answer.lower() for keyword in keywords)
    return {
        "refused": refused,
        "refusal_correct": refused == unanswerable,
        "keyword_recall": None if unanswerable else keyword_hits / max(len(keywords), 1),
        "answer_token_f1": None if unanswerable else token_f1(item.get("answer", ""), answer),
        "citation_count": len(unique_citations),
        "citation_validity": (len(valid_citations) / len(unique_citations) if unique_citations else 0.0),
        "expected_source_cited": None if unanswerable else source_cited,
    }


def _parse_judge_payload(text: str) -> dict:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise RuntimeError("LLM judge did not return a JSON object")
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise RuntimeError("LLM judge returned invalid JSON") from exc
    for key in ("faithfulness", "answer_relevancy"):
        value = payload.get(key)
        if not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
            raise RuntimeError(f"LLM judge returned invalid {key}")
        payload[key] = float(value)
    return payload


def judge_answer(
    question: str,
    answer: str,
    hits: list[dict],
    backend: ChatBackend,
    *,
    model: str | None = None,
) -> dict:
    system = (
        "你是严格的 RAG 评测器。仅根据给定问题、回答和检索证据评分。"
        "faithfulness 表示回答中的事实是否都能被证据支持；answer_relevancy 表示回答是否直接解决问题。"
        "两个分数范围均为 0 到 1。只输出 JSON："
        '{"faithfulness":0.0,"answer_relevancy":0.0,"reason":"简短原因"}'
    )
    user = f"问题：{question}\n\n回答：{answer}\n\n检索证据：\n{format_results(hits)}"
    return _parse_judge_payload(backend.complete(system, user, model=model))


def aggregate_e2e_metrics(cases: list[dict]) -> dict:
    if not cases:
        return {}
    answerable = [case for case in cases if not case["unanswerable"]]
    judged = [case for case in cases if case.get("judge")]

    def average(values: list[float]) -> float | None:
        return mean(values) if values else None

    return {
        "case_count": len(cases),
        "answerable_count": len(answerable),
        "unanswerable_count": len(cases) - len(answerable),
        "refusal_accuracy": average([float(case["metrics"]["refusal_correct"]) for case in cases]),
        "keyword_recall": average([float(case["metrics"]["keyword_recall"]) for case in answerable]),
        "answer_token_f1": average([float(case["metrics"]["answer_token_f1"]) for case in answerable]),
        "citation_validity": average([float(case["metrics"]["citation_validity"]) for case in answerable]),
        "expected_source_citation_rate": average([float(case["metrics"]["expected_source_cited"]) for case in answerable]),
        "faithfulness": average([float(case["judge"]["faithfulness"]) for case in judged]),
        "answer_relevancy": average([float(case["judge"]["answer_relevancy"]) for case in judged]),
        "judged_count": len(judged),
    }
