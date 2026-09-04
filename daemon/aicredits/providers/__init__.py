"""Adapter package. Importing it registers every adapter in base.REGISTRY."""

from . import alibaba, anthropic, antigravity, codex, grok, nous, openrouter, zai  # noqa: F401
from .base import REGISTRY, Provider  # noqa: F401
