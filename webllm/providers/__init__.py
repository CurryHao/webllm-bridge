from __future__ import annotations

from webllm.providers.antafu import AntafuProvider
from webllm.providers.base import Capture, ProviderSpec, WebProvider
from webllm.providers.deepseek import DeepSeekProvider
from webllm.providers.kimi import KimiProvider
from webllm.providers.qwen import QwenProvider
from webllm.providers.wenxin import WenxinProvider

_PROVIDER_TYPES = (
    DeepSeekProvider,
    QwenProvider,
    KimiProvider,
    WenxinProvider,
    AntafuProvider,
)

PROVIDERS: dict[str, WebProvider] = {
    provider_type.spec.name: provider_type() for provider_type in _PROVIDER_TYPES
}


def get_provider(name: str) -> WebProvider:
    try:
        return PROVIDERS[name]
    except KeyError:
        supported = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"Unknown provider: {name}. Supported providers: {supported}") from None


def list_providers() -> list[dict[str, object]]:
    return [
        {
            "name": provider.spec.name,
            "display_name": provider.spec.display_name,
            "url": provider.spec.url,
            "supports_new_session": provider.spec.supports_new_session,
            "supports_sources": provider.spec.supports_sources,
        }
        for provider in PROVIDERS.values()
    ]


__all__ = [
    "Capture",
    "PROVIDERS",
    "ProviderSpec",
    "WebProvider",
    "get_provider",
    "list_providers",
]
