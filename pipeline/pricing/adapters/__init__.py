"""Eight source-local adapters behind the preserved lookup protocol."""
from typing import Protocol
from ..base import ContentSnapshot, ExtractionResult
from .openai import OpenAIPricingExtractor
from .deepseek import DeepSeekPricingExtractor
from .glm import GlmPricingExtractor
from .kimi import KimiPricingExtractor
from .doubao import DoubaoPricingExtractor
from .qwen import QwenPricingExtractor
from .anthropic import AnthropicPricingExtractor
from .google import GooglePricingExtractor
from .vertex import VertexPricingExtractor

class SourceExtractor(Protocol):
    def extract(self, snapshot: ContentSnapshot) -> ExtractionResult: ...

_EXTRACTORS: dict[str, SourceExtractor] = {
    "openai:pricing": OpenAIPricingExtractor(),
    "deepseek:pricing": DeepSeekPricingExtractor(),
    "glm:pricing": GlmPricingExtractor(),
    "kimi:pricing": KimiPricingExtractor(),
    "doubao:pricing": DoubaoPricingExtractor(),
    "qwen:pricing": QwenPricingExtractor(),
    "anthropic:pricing": AnthropicPricingExtractor(),
    "google:pricing": GooglePricingExtractor(),
    "vertex-google:pricing": VertexPricingExtractor("vertex-google"),
    "vertex-anthropic:pricing": VertexPricingExtractor("vertex-anthropic"),
}

def get_extractor(source_key: str) -> SourceExtractor | None:
    return _EXTRACTORS.get(source_key)
