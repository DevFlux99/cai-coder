import json
from pathlib import Path
from typing import Callable, Awaitable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool

from agent.prompt import get_working_dir
from agent.utils import common_util
from agent.utils.skill import (
SkillRecord,
render_skills_json,
parse_skill_md
)


@tool
def load_skill(skill_name: str) -> str:
    """Load the full content of a skill into the agent's context.

    Use this when you need detailed information about how to handle a specific
    type of request. This will provide you with comprehensive instructions,
    policies, and guidelines for the skill area.

    Args:
        skill_name: The name of the skill to load (e.g., "expense_reporting", "travel_booking")
    """
    # Find and return the requested skill
    for skill in SKILLS:
        if skill["name"] == skill_name:
            skill_md_path = Path(skill['location'])
            skill_record: SkillRecord = parse_skill_md(skill_md_path,read_body_now = True)
            return f"Loaded skill: {skill_name}\n\n{skill_record.content}"

    # Skill not found
    available = ", ".join(skill['name'] for skill in SKILLS)
    return f"Skill '{skill_name}' not found. Available skills: {available}"

class SkillMiddleware(AgentMiddleware):
    """Middleware that injects skill descriptions into the system prompt."""

    # Register the load_skill tool as a class variable
    tools = [load_skill]

    def __init__(self):
        """Initialize and generate the skills prompt from SKILLS."""
        # Build skills prompt from the SKILLS list
        skills_list = []
        for skill in SKILLS:
            skills_list.append(
                f"- **{skill['name']}**: {skill['description']}"
            )
        self.skills_prompt = "\n".join(skills_list)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Sync: Inject skill descriptions into system prompt."""
        # Build the skills addendum
        skills_addendum = (
            SKILL_PROMPT +
            f"\n## Skill Pool\nBelow is the list of loadable skills. \n{self.skills_prompt}\n"
        )

        # Append to system message content blocks
        new_content = list(request.system_message.content_blocks) + [
            {"type": "text", "text": skills_addendum}
        ]
        new_system_message = SystemMessage(content=new_content)
        modified_request = request.override(system_message=new_system_message)
        return handler(modified_request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """Sync: Inject skill descriptions into system prompt."""
        # Build the skills addendum
        skills_addendum = (
            SKILL_PROMPT +
            f"\n## Skill Pool\nBelow is the list of loadable skills. \n{self.skills_prompt}\n"
        )

        # Append to system message content blocks
        new_content = list(request.system_message.content_blocks) + [
            {"type": "text", "text": skills_addendum}
        ]
        new_system_message = SystemMessage(content=new_content)
        modified_request = request.override(system_message=new_system_message)

        for attempt in range(3):
            try:
                return await handler(modified_request)
            except Exception:
                if attempt == 2:
                    raise
        return None


_skills_json = render_skills_json(
    Path(get_working_dir("WORKING_DIR", common_util.find_project_root())) / 'skills')
skillDict: dict = json.loads(_skills_json) if _skills_json else {}


SKILLS: list[SkillRecord] = skillDict.get("available_skills") or []

SKILL_PROMPT = """

Role: Progressive Skill Loading Agent

## Core Principle
You are an AI equipped with a “Progressive Skill Loading” mechanism. 
You must never activate all capabilities and personas at the very beginning; instead, you must always maintain a minimalist [Base State]. 
Only when the user’s input explicitly triggers specific conditions will you internally “load” the corresponding Skill and respond according to that Skill’s rules and perspective. 
When the topic ends, you automatically “unload” that Skill and return to the Base State.

## Execution Workflow
Before every response, you must execute the following state machine logic in the background (do not output this process; use it strictly for internal thinking):

[State Detection]: What is the current state? (Base State / Loaded Skill A / Loaded Skill B…)
[Trigger Evaluation]: Does the user’s latest input satisfy the trigger conditions for any Skill?
If yes and currently unloaded -> [Load Skill]: Read the Skill’s system prompt, persona, and constraints, and respond accordingly.
If yes and currently loaded -> [Maintain Skill]: Continue responding as the current Skill.
If no and currently loaded -> [Unload Skill]: Smoothly conclude the current Skill’s perspective, return to the Base State, and respond as a normal AI.
If no and in the Base State -> [Base Response]: Respond briefly and neutrally as a standard assistant.

## How to Load Skills
Use the `load_skill` tool when you need detailed information.

"""

