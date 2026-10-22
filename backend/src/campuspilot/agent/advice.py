"""Evidence-scoped clarifications and logical limits; no generated university facts."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from campuspilot.agent.evidence import Evidence
from campuspilot.retrieval.applicability import page_status_question


@dataclass(frozen=True)
class Advice:
    answer: str
    status: Literal["limited", "needs_clarification"] = "limited"
    cited: tuple[str, ...] = ()


def evidence_advice(question: str, history: Sequence[str], ev: Evidence) -> Advice | None:
    # A declared channel establishes that channel, not the absence of all alternatives.
    # Use only an explicit source field; unrelated mentions of "online" prove nothing.
    channel_question = re.search(
        r"(?:可[以否]?|能(?:否|不能)?|是否|允许|有(?:没有|无)|支持).{0,10}(?:线下|现场|窗口)"
        r"|(?:线下|现场|窗口).{0,10}(?:可[以否]?|能(?:否|不能)?|是否|允许|支持)", question,
    )
    if (channel_question and re.search(r"提交|办理|受理|申请", question)
            and re.search(r"指南|文字|页面", question)):
        for hit in ev.grounded_hits():
            source = hit.get("source_id")
            if not isinstance(source, str) or source not in ev.allowed:
                continue
            field = re.search(r"办理(?:方式|途径)[ \t:：]*(线上办理|网上办理|线上|网上)",
                              str(hit.get("text", "")))
            if field is None:
                continue
            source_text = "\n".join(str(row.get("text", "")) for row in ev.grounded_hits()
                                    if row.get("source_id") == source)
            if re.search(r"线下|现场|窗口|仅限|只能|不得|不支持|不受理", source_text):
                continue  # Explicit alternatives/exclusions need the full evidence path.
            return Advice(
                f"这份指南明确列出的办理方式是“{field[1]}”，无法确认是否另有线下受理。"
                "没有列出线下渠道不能排除其他受理安排；请按已列的线上渠道办理，"
                "如需现场提交，先向该事项主管部门核实。",
                cited=(source,),
            )
    if page_status_question(question):
        hits = [h for h in ev.hits if re.search(
            r"停[止用]|不再提供|废止", str(h.get("title", "")) + str(h.get("text", "")),
        )]
        cited = tuple(dict.fromkeys(str(h["source_id"]) for h in hits
                                    if h.get("source_id") in ev.allowed))
        return Advice(
            "重新抓取成功只说明页面可以读取，不能证明页面所述服务已恢复。"
            + ("所引旧页面有停止服务的说明，也不能据抓取时间推断该说明已被撤销。" if cited else "")
            + "请查看主管部门明确的现行服务公告，核实当前服务状态和使用入口。",
            cited=cited,
        )
    if (
        re.search(r"(?:未|没|没有).{0,4}(?:写|列|提).{0,5}(?:收费|费用)", question)
        and re.search(r"保证|永[久远]免费|一直免费|所有项目|全部免费", question)
    ):
        return Advice("页面未列收费项目，不能据此保证所有项目永久免费。"
                      "具体项目是否收费、收费范围以及后续通知是否调整，都需向该项目主管部门核实。")
    # A cohort-bound loan notice cannot establish another student's applicable procedure.
    # Years come from evidence, and bank/cohort confirmations come only from user messages.
    if not re.search(r"贷款|毕业确认", question) or re.search(r"新生|入学|回执", question):
        return None
    if re.search(r"历史|当年|原通知|当时|通知.*(?:原文|怎么写|写了)", question):
        return None
    if re.search(r"是不是|是否|等于|意味着", question) and re.search(r"还清|还款", question):
        # Explain the distinction when supported; an individual repayment procedure is separate.
        if not re.search(r"怎么|如何|哪[个家]|办理|更改|修改|渠道", question):
            return None
    hits = [h for h in ev.hits if "毕业确认" in str(h.get("title", ""))
            + str(h.get("source_title", "")) and h.get("source_id") in ev.allowed]
    cohorts = sorted({y for h in hits for y in re.findall(
        r"(20\d{2})\s*届", str(h.get("title", "")) + str(h.get("source_title", "")),
    )})
    if not cohorts:
        return None
    messages = [question, *reversed([text for text in history[-8:] if "贷款" in text
                                   or "毕业确认" in text])]
    user_cohort = next((m[1] or m[2] for text in messages
                        if (m := re.search(r"(20\d{2})\s*届|(?:于)?(20\d{2})年毕业", text))), None)
    banks = (r"国家开发银行|国开行|中国银行|中行|农业银行|建设银行|工商银行|交通银行"
             r"|邮储银行|农商银行|农信")
    bank = next((m[0] for text in messages if (m := re.search(banks, text))), None)
    if re.search(r"银行不在|银行不详|其他银行|不知道.{0,5}银行|不清楚.{0,5}银行", question):
        bank = None
    if user_cohort in cohorts and bank:
        return None
    cited = tuple(dict.fromkeys(str(h["source_id"]) for h in hits))
    missing = []
    if not user_cohort:
        missing.append("你的毕业届次")
    if not bank:
        missing.append("贷款由哪家银行经办")
    request = "请先确认" + "，以及".join(missing) + "。" if missing else (
        "你提供的毕业届次与现有通知范围不同。"
    )
    known = f"已知经办银行是{bank}。" if bank else ""
    scope = "、".join(y + "届" for y in cohorts)
    return Advice(
        known + request + f"当前取得的是{scope}贷款毕业确认通知，不能直接当作你当前适用的流程。"
        "确认后请从经办银行官方渠道或资助管理中心核对现行手续；收到短信时先核实来源。",
        "needs_clarification" if missing else "limited", cited,
    )
