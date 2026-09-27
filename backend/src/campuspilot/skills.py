from dataclasses import dataclass

from campuspilot.contracts import SkillDescriptor
from campuspilot.interfaces import Skill


@dataclass(frozen=True)
class GuidanceSkill:
    descriptor: SkillDescriptor


class StaticSkillRegistry:
    def __init__(self, skills: tuple[Skill, ...], available_tools: frozenset[str]) -> None:
        self._skills: dict[str, SkillDescriptor] = {}
        for skill in skills:
            descriptor = SkillDescriptor.model_validate(skill.descriptor.model_dump())
            if descriptor.skill_id in self._skills:
                raise ValueError("Duplicate Skill")
            if len(set(descriptor.required_tools)) != len(descriptor.required_tools):
                raise ValueError("Duplicate tool dependency")
            if not set(descriptor.required_tools) <= available_tools:
                raise ValueError("Unknown tool dependency")
            self._skills[descriptor.skill_id] = descriptor

    def get(self, skill_id: str) -> SkillDescriptor:
        return self._skills[skill_id]


def demo_skill() -> GuidanceSkill:
    return GuidanceSkill(
        SkillDescriptor(
            skill_id="synthetic-campus-guide",
            description="Synthetic service, office and route demonstration",
            instructions="Use registered mock tools; never claim real campus task completion.",
            required_tools=("search_service", "find_office", "route_plan"),
            completion_criteria="Three synthetic results with evidence",
            risk="public_read",
        )
    )
