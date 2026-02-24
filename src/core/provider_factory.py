"""Provider factory — creates LLMProvider instances from EngineConfig."""

from __future__ import annotations

from typing import Any, Callable, Coroutine

from src.core.config import EngineConfig
from src.core.llm_provider import LLMProvider
from src.core.logging_config import get_logger
from src.core.models import ExtensionConfig

logger = get_logger(__name__)


def create_provider_factory(
    config: EngineConfig,
    extension_config: ExtensionConfig | None = None,
) -> Callable[[], Coroutine[Any, Any, LLMProvider]]:
    """Return an async factory that creates *connected* :class:`LLMProvider` instances.

    The returned callable is suitable for both the prewarm pool and cold-start
    paths in :class:`SessionManager`.
    """
    if config.provider == "bedrock":
        from src.core.providers.bedrock import BedrockProvider

        async def bedrock_factory() -> LLMProvider:
            provider = BedrockProvider(
                config=config.bedrock,
                engine=config.engine,
                extension_config=extension_config,
            )
            await provider.connect()
            return provider

        return bedrock_factory

    if config.provider == "litellm":
        from src.core.providers.litellm_provider import LiteLLMProvider

        async def litellm_factory() -> LLMProvider:
            provider = LiteLLMProvider(config=config.litellm)
            await provider.connect()
            return provider

        return litellm_factory

    raise ValueError(f"Unknown provider: {config.provider!r}")


def create_resume_provider_factory(
    config: EngineConfig,
    extension_config: ExtensionConfig | None = None,
) -> Callable[..., Coroutine[Any, Any, LLMProvider]] | None:
    """Return an async factory for *resuming* sessions, or ``None`` if unsupported.

    Only the Bedrock provider supports native session resume via the SDK's
    ``resume`` option.  LiteLLM has no equivalent — callers should fall back
    to creating a fresh session.
    """
    if config.provider == "bedrock":
        from src.core.providers.bedrock import BedrockProvider

        async def bedrock_resume_factory(resume_session_id: str) -> LLMProvider:
            provider = BedrockProvider(
                config=config.bedrock,
                engine=config.engine,
                extension_config=extension_config,
                resume_session_id=resume_session_id,
            )
            await provider.connect()
            return provider

        return bedrock_resume_factory

    # LiteLLM has no native session resume support
    return None
