from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class LLMSelector:
    provider: str
    model: str

    @property
    def key(self) -> str:
        return f"{self.provider}/{self.model}"

    def as_tuple(self) -> Tuple[str, str]:
        return self.provider, self.model


def parse_llm_selector(value: Optional[str]) -> Optional[LLMSelector]:
    """Parse a runtime selector formatted as provider/model."""
    if value is None:
        return None

    provider, separator, model = value.strip().partition("/")
    if not separator or not provider.strip() or not model.strip():
        raise ValueError("LLM selector must look like provider/model, for example openai/gpt-5.5.")

    return LLMSelector(provider=provider.strip(), model=model.strip())


def split_llm_selector(value: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    selector = parse_llm_selector(value)
    if selector is None:
        return None, None
    return selector.provider, selector.model
