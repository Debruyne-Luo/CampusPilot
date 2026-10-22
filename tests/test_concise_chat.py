"""Observable concise-mode contracts using the real directory and synthetic model."""

import asyncio
from typing import Any

from campuspilot.agent.executor import AgentRunner
from campuspilot.chat_runtime import ConversationContext
from campuspilot.knowledge import KnowledgeStore
from campuspilot.tools import agent_registry
from test_agent_loop import CARD, CARD_EVIDENCE, DATA, REPO, FakeLLM, answer, understood


def concise(model: FakeLLM | None = None) -> AgentRunner:
    return AgentRunner(agent_registry(REPO, KnowledgeStore.load(DATA / 'knowledge.json')),
                       REPO, model, concise=True)


def run(agent: AgentRunner, question: str, context: ConversationContext) -> dict[str, Any]:
    return asyncio.run(agent.run(question, context))


def test_card_loss_gives_named_miniapp_without_model_or_checklist() -> None:
    model = FakeLLM()
    result = run(concise(model), '校园卡挂失怎么办', ConversationContext())
    assert not model.calls
    assert result['result_status'] == 'success'
    assert '成理校园卡' in result['answer'] and '小程序' in result['answer']
    assert not result.get('checklist')
    assert [s['tool'] for s in result['plan']] == ['search_service']
    assert result['citations'] and len(result['answer']) < 250


def test_direct_service_highlights_channel_and_conditions_with_materials_in_details() -> None:
    from campuspilot.agent.quick_answers import service_answer

    assert CARD is not None
    service = CARD.model_copy(update={
        'entry_points': ('SYNTHETIC 合成食堂服务区',),
        'required_materials': ('SYNTHETIC 合成证件',),
        'limits': ('SYNTHETIC 余额大于20元，不是工本费',),
    })
    text = service_answer(service, 'SYNTHETIC 在哪里办')
    assert text is not None and text.startswith('**办理入口：**')
    assert '\n\n**注意：**' in text
    assert '合成证件' not in text
    assert '余额大于20元，不是工本费' in text


def test_exact_place_query_avoids_model_and_returns_map_action() -> None:
    model = FakeLLM()
    result = run(concise(model), '东区图书馆在哪', ConversationContext())
    assert not model.calls and result['answer_mode'] == 'agent_place'
    assert len(result['places']) == 1 and result['places'][0]['name'] == '东区图书馆'
    assert result['map_actions']


def test_online_request_has_no_offline_map_and_both_channels_remain_available() -> None:
    online = run(concise(), '校园卡挂失线上入口在哪', ConversationContext())
    assert '成理校园卡' in online['answer'] and '食堂' not in online['answer']
    assert not online['places'] and not online['map_actions']
    both = run(concise(), '校园卡挂失线上线下在哪办', ConversationContext())
    assert '成理校园卡' in both['answer'] and '食堂' in both['answer']


def test_followup_materials_is_explicit_and_topic_switch_clears_service_focus() -> None:
    context = ConversationContext()
    model = FakeLLM(understood(service='校园卡补办'), answer(
        '带本人身份证，自助补卡前确认卡内余额大于20元。', [CARD_EVIDENCE[0]],
    ))
    agent = concise(model)
    first = run(agent, '校园卡补办在哪里办', context)
    assert first['result_status'] == 'success' and not first.get('checklist')
    second = run(agent, '要带什么材料', context)
    assert second.get('checklist') and second['checklist']['service_id'].endswith('replacement')
    third = run(agent, '东区图书馆在哪', context)
    assert not third['services'] and context.service_focus is None


def test_latest_and_combined_queries_do_not_take_fast_service_path() -> None:
    for question in ['校园卡挂失最新规定是什么', '校园卡挂失和图书馆在哪里']:
        model = FakeLLM(understood('政策问答'), answer('暂无足够依据。', [], 'empty'))
        asyncio.run(concise(model).run(question, ConversationContext()))
        assert model.calls, question


def test_other_campus_context_does_not_use_chengdu_directory_shortcut() -> None:
    model = FakeLLM(understood('政策问答'), answer('现有资料无法确认宜宾校区安排。', [], 'empty'))
    result = run(concise(model), '校园卡挂失怎么办', ConversationContext(campus='yibin'))
    assert model.calls and result['answer_mode'] != 'agent_direct'


def test_place_name_inside_a_different_destination_needs_understanding() -> None:
    from campuspilot.agent.quick_answers import quick_view

    for question in ['东区图书馆附近药店在哪', '宜宾校区东区图书馆在哪里', '东区图书馆快递柜在哪']:
        assert quick_view(question, REPO) is None, question


def test_materials_tool_is_not_offered_or_executed_without_a_request() -> None:
    from campuspilot.agent.evidence import Evidence
    from campuspilot.agent.understand import Understanding

    model = FakeLLM(answer('暂无足够依据。', [], 'empty'))
    agent = concise(model)
    evidence = Evidence(question='校园卡使用规则是什么', answering=True)
    status = asyncio.run(agent._call('make_checklist', {
        'service_id': 'cdut:service:card-replacement', 'audience': 'all',
    }, evidence))
    assert status == 'not_requested' and evidence.checklist is None
    asyncio.run(agent._answer(evidence.question, Understanding(intent='政策问答'),
                              ConversationContext(), evidence))
    schema_text = str(model.calls[0])
    assert 'make_checklist' not in schema_text


def test_answer_model_is_told_when_the_page_already_has_detailed_procedures() -> None:
    from campuspilot.agent.evidence import Evidence
    from campuspilot.agent.understand import Understanding

    assert CARD is not None and CARD.steps
    for level, steps, available in [('procedure', CARD.steps, True),
                                    ('guide', (), False), ('procedure', (), False)]:
        model = FakeLLM(answer('SYNTHETIC 简要答复。', [], 'empty'))
        ev = Evidence(services={'synthetic:service': CARD.model_copy(update={
            'information_level': level, 'steps': steps,
        })})
        asyncio.run(concise(model)._answer('SYNTHETIC 怎么办', Understanding(intent='办事'),
                                          ConversationContext(), ev))
        systems = [m['content'] for m in model.calls[0]['messages'] if m['role'] == 'system']
        assert any('本轮页面已提供' in str(message) for message in systems) is available
        assert any('本轮页面没有' in str(message) for message in systems) is not available


def test_presentation_context_updates_after_a_model_requested_service_search() -> None:
    from campuspilot.agent.evidence import Evidence
    from campuspilot.agent.understand import Understanding
    from campuspilot.llm.chat_model import Completion, ToolCall

    seen = []

    def search(messages: list[dict[str, object]]) -> Completion:
        seen.append(any('本轮页面没有' in str(m['content']) for m in messages))
        return Completion(tool_calls=(ToolCall(call_id='synthetic:search', name='search_service',
                          arguments='{"query":"校园卡补办"}'),))

    def respond(messages: list[dict[str, object]]) -> Completion:
        seen.append(any('本轮页面已提供' in str(m['content']) for m in messages))
        return answer('SYNTHETIC 简要答复。', [], 'empty')

    asyncio.run(concise(FakeLLM(search, respond))._answer(
        'SYNTHETIC 怎么办', Understanding(intent='办事'), ConversationContext(), Evidence(),
    ))
    assert seen == [True, True]


def test_concise_answer_has_no_automatic_scope_notice_but_keeps_metadata() -> None:
    from campuspilot.agent.evidence import Evidence

    ev = Evidence(hits=[
        {'chunk_id': 'SYNTHETIC-a', 'source_id': 'SYNTHETIC-source', 'title': 'SYNTHETIC-A',
         'scope_notes': ['来源适用校区尚未确认', '2026级本科生适用']},
        {'chunk_id': 'SYNTHETIC-b', 'source_id': 'SYNTHETIC-source', 'title': 'SYNTHETIC-B',
         'scope_notes': ['来源适用校区尚未确认']},
    ])
    result = concise().responses.build(
        answer='SYNTHETIC 简要答复。', status='success', view=None, plan=None, steps=[], ev=ev,
        cited=('SYNTHETIC-source',),
    )
    text = str(result['answer'])
    assert text == 'SYNTHETIC 简要答复。'
    assert ev.hits[0]['scope_notes'] == ['来源适用校区尚未确认', '2026级本科生适用']


def test_latest_question_does_not_expand_stale_facts_after_web_is_unverified() -> None:
    from campuspilot.agent.evidence import Evidence
    from campuspilot.agent.plan import Plan
    from campuspilot.agent.understand import Understanding
    from campuspilot.web_evidence import WebSearchResult

    class EmptySearch:
        async def search(self, question: str) -> WebSearchResult:
            return WebSearchResult('limited')

    model = FakeLLM(answer('SYNTHETIC 旧批次日期。', ['SYNTHETIC-old']))
    agent = concise(model)
    agent.web_service = EmptySearch()  # type: ignore[assignment]
    ev = Evidence(hits=[{'source_id': 'SYNTHETIC-old', 'chunk_id': 'SYNTHETIC-chunk',
                         'text': 'SYNTHETIC 旧批次日期。', 'stale': True}],
                  allowed={'SYNTHETIC-old'})
    result = asyncio.run(agent._with_web(
        '请查最新通知', Understanding(intent='政策问答'), ConversationContext(), ev, Plan(), [],
    ))
    assert not model.calls
    assert '旧批次日期' not in str(result['answer'])
    assert result['result_status'] == 'limited'
