"""Skill schemas, file-based registry (skills/*.yaml), and policy-respecting engine."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class Skill(BaseModel):
    name: str
    description: str = ""
    version: str = "0.1.0"
    instructions: str = ""
    inputs: dict = {}
    outputs: dict = {}
    required_tools: list[str] = []
    required_permissions: list[str] = []
    agent: str = "personal"


class SkillRegistry:
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = skills_dir
        self.skills: dict[str, Skill] = {}
        self.reload()

    def reload(self) -> None:
        candidates = [Path(self.skills_dir)]
        # also try repo-root skills/ when running from backend/
        if Path("../skills").exists():
            candidates.append(Path("../skills"))
        self.skills = {}
        for base in candidates:
            if not base.exists():
                continue
            for yaml_file in sorted(base.glob("*/skill.yaml")):
                try:
                    data = yaml.safe_load(yaml_file.read_text()) or {}
                    self.skills[data.get("name", yaml_file.parent.name)] = Skill(**data)
                except Exception:
                    continue

    def list(self) -> list[Skill]:
        return list(self.skills.values())

    def match(self, text: str) -> Skill | None:
        t = text.lower()
        keywords = {"meeting-preparation": ["meeting", "brief", "prepare"],
                    "daily-planning": ["daily plan", "plan my day", "today's plan", "todays plan"],
                    "research": ["research", "paper", "analyze"],
                    "project-status": ["project status", "status", "standup"]}
        for name, kws in keywords.items():
            if name in self.skills and any(k in t for k in kws):
                return self.skills[name]
        for skill in self.skills.values():
            if skill.name.lower().replace("-", " ") in t or skill.name.lower() in t:
                return skill
        return None
