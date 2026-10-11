"""Short, grounded answers for explicit campus entities and curated life discovery."""

from pydantic import JsonValue

from campuspilot.directory.repository import DirectoryRepository
from campuspilot.domain import CampusPlace
from campuspilot.presentation import AnswerEnvelope, guide_answer, place_card, service_card


def campus_answer(repository: DirectoryRepository, question: str) -> dict[str, JsonValue] | None:
    text = question.casefold()
    if (
        not any(x in text for x in ("银行卡", "公交卡", "交通卡", "学生证"))
        and any(x in text for x in ("补卡", "补办"))
        and any(x in text for x in ("校园卡", "一卡通", "补卡"))
    ):
        service = repository.find_service("cdut:service:campus-card-replacement")
        if service:
            reply = AnswerEnvelope(
                schema_version=1,
                status="success",
                answer="需要查询具体要求。",
                service_ids=(service.service_id,),
            )
            answer = guide_answer(repository, reply, question)
            if answer != reply.answer:
                return response(
                    answer,
                    repository.service_places(service),
                    services=[service_card(repository, service)],
                    nearby="replacement",
                )

    # Named shop/building/wing wins over broad discovery, unless discovery is explicit.
    named = repository.match_places_in_question(question)
    discovery = any(x in text for x in ("推荐", "有哪些", "有什么", "吃什么", "哪里吃", "哪儿吃"))
    food = any(x in text for x in ("吃", "美食", "餐饮", "餐厅", "饭", "食堂", "早餐", "奶茶"))
    parcel = any(x in text for x in ("快递", "取件", "拿包裹", "拿件", "寄件"))
    if parcel and not any("parcel" in (p.tags or ()) for p in named):
        selected = tuple(p for p in repository.search_place() if "parcel" in (p.tags or ()))
        return response(
            "**拿快递：**理工东苑左转的菜鸟驿站、京东派、顺丰。\n"
            "先看取件短信/物流详情，去对应站点；三处位置不同，下方可分别查看地图和步行路线。",
            selected,
            nearby="parcel",
        )
    if food and (discovery or not named):
        areas = {
            tag
            for words, tag in (
                (("芙蓉",), "furong"),
                (("珙桐", "拱桐"), "gongtong"),
                (("东苑", "校外", "学校周围", "学校外"), "dongyuan"),
            )
            if any(word in text for word in words)
        }
        if not areas:
            areas = {"furong", "gongtong"}
            if not any(x in text for x in ("校内", "学校里", "学校内", "食堂")):
                areas.add("dongyuan")
        selected = tuple(
            p
            for p in repository.search_place()
            if "food" in (p.tags or ()) and areas.intersection(p.tags or ())
        )
        lines = []
        if "furong" in areas:
            lines.append("**芙蓉食堂：**达美乐（披萨）、麦当劳、赛百味（三明治）。")
        if "gongtong" in areas:
            lines.append("**珙桐食堂：**肯德基（KFC）、吉野家。")
        if "dongyuan" in areas:
            lines.append(
                "**理工东苑附近：**沙县小吃、小笼包；想吃干锅可看奇味干锅，"
                "烧烤可看胡师烧烤，饮品有蜜雪冰城。"
            )
        answer = "\n".join(lines)
        return response(
            answer + "\n下方可看地点和步行路线；营业与菜单以门店为准。", selected, nearby="food"
        )
    if named and not any(x in text for x in ("老师", "补卡", "挂失", "补办", "余额", "费用")):
        if len(named) == 1:
            place = named[0]
            answer = f"**{place.name}**。"
            if any(x in text for x in ("营业", "开门", "关门", "价格", "价钱", "多少钱", "菜单")):
                answer += "当前营业时间与菜单价格暂未收录，请以门店信息为准。"
            if place.address_detail:
                answer += place.address_detail
            if place.position:
                answer += "\n下方可查看地图，选择起点规划步行路线。"
            else:
                answer += "\n分区已收录，独立地图点位尚未确认；可在地图上手动选目的地。"
            kind = (
                "food"
                if "food" in (place.tags or ())
                else "parcel"
                if "parcel" in (place.tags or ())
                else None
            )
            return response(answer, named, nearby=kind)
        return response("找到这些地点，可按名称选择查看地图。", named)
    return None


def response(
    answer: str,
    places: tuple[CampusPlace, ...],
    *,
    services: list[JsonValue] | None = None,
    nearby: str | None = None,
) -> dict[str, JsonValue]:
    return {
        "answer": answer,
        "answer_mode": "campus_retrieval",
        "result_status": "success",
        "services": services or [],
        "teachers": [],
        "places": [place_card(p) for p in places],
        "nearby_kind": nearby,
        "notice": "地点依据见详情；地图点位不表示当前营业或设备入口。",
        "excerpts": [],
    }
