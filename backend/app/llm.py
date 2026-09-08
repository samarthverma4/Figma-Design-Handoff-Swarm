"""Azure OpenAI chat model factory for the swarm agents."""
from __future__ import annotations

from langchain_openai import AzureChatOpenAI

from .config import Settings


def build_model(settings: Settings) -> AzureChatOpenAI:
    """Construct the GPT deployment the agents reason with.

    Uses the Azure OpenAI deployment named by AZURE_OPENAI_DEPLOYMENT
    (default: gpt-4.1-nano). temperature=0 keeps handoff decisions stable.
    """
    return AzureChatOpenAI(
        azure_endpoint=settings.azure_endpoint,
        azure_deployment=settings.azure_deployment,
        api_version=settings.azure_api_version,
        api_key=settings.azure_api_key,
        temperature=0,
        timeout=60,
        max_retries=2,
    )
