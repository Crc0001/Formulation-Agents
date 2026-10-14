"""研究上下文必须有确定性体积预算。

实测：run['message'] 会递归携带上一轮整份 payload，2026-10-13 的 102-2 首请求达到
187,548 字符，占满 300 秒模型窗口后仍被应用层判超时。这里锁死 research_context 的
输出长度上限与 request 摘录上限。
"""
import json

from virtual_reactor_api.capsule_research import research_context

BUDGET = 45000


def _snapshot(evidence_text, runs=3, formulations=120, evidence_count=60):
    evidence = [
        {
            "id": f"e{i}",
            "title": "来源标题" * 20,
            "text": evidence_text,
            "basis": "source",
            "access": "public",
            "source_url": "https://example.org/a",
            "locator": "第6.1节",
            "applicability": "适用性说明" * 30,
            "fields": {"source_verification_json": "x" * 200},
        }
        for i in range(evidence_count)
    ]
    runs_payload = [
        {
            "id": f"r{i}",
            "message": "历史请求" * 2000,
            "report": {
                "summary": "历史摘要" * 500,
                "gaps": ["缺口" * 200] * 20,
                "formulations": [
                    {
                        "title": f"候选{j}",
                        "dosage_form": "片剂",
                        "source_role": "official_label",
                        "source_ids": "s1 s2",
                        "batch_units": None,
                        "strength_mg": 10.0,
                        "strength_basis": "salt",
                        "components": [
                            {"name": "辅料", "compartment": "core", "amount_mg": 1.0, "batch_amount": 100.0, "batch_mass_unit": "g", "percent": 1.0, "grade": "A"}
                        ],
                        "applicability": "适用性" * 100,
                    }
                    for j in range(formulations)
                ],
                "processes": [{"title": f"工艺{j}", "scope": "s", "source_ids": "s1"} for j in range(formulations)],
            },
        }
        for i in range(runs)
    ]
    return {
        "evidence": evidence,
        "runs": runs_payload,
        "project": {"id": "p", "name": "项目", "api": "API"},
        "tasks": [],
    }


def test_origin_context_respects_budget_even_with_huge_message():
    huge_message = "【原研及处方工艺】" + json.dumps(_snapshot("x", 1), ensure_ascii=False) * 4
    assert len(huge_message) > 150000
    context = research_context(_snapshot("原文" * 4000), huge_message)
    serialized = json.dumps(context, ensure_ascii=False)
    assert len(serialized) <= BUDGET + 2000, len(serialized)
    assert len(context["request"]) <= 12000
    assert context["request_is_text_excerpt"] is True
    assert context["request_truncated"] is True
    assert context["context_chars"] <= BUDGET + 2000
    assert "不要尝试解析" in context["reading_note"]


def test_small_context_is_not_trimmed():
    context = research_context(_snapshot("短原文", runs=1, formulations=1, evidence_count=4), "【原研及处方工艺】小请求")
    assert context["context_trimmed"] is False
    assert context["request_truncated"] is False
    assert context["request"] == "【原研及处方工艺】小请求"
    assert len(context["evidence"]) == 4


def test_non_origin_context_also_bounded():
    huge_message = "【处方辅料筛选】" + "y" * 50000
    context = research_context(_snapshot("原文" * 4000), huge_message)
    assert len(context["request"]) <= 12000
    assert json.dumps(context, ensure_ascii=False).__len__() <= BUDGET + 2000


