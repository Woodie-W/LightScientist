from __future__ import annotations

from importlib import resources


def load_prompt(name: str) -> str:
    return resources.files(__package__).joinpath(f"{name}.md").read_text(encoding="utf-8").strip()
