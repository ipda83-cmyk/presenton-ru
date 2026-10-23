from enum import Enum


class WebSearchProvider(Enum):
    AUTO = "auto"
    NATIVE = "native"
    SEARXNG = "searxng"
    TAVILY = "tavily"
    EXA = "exa"
    BRAVE = "brave"
    SERPER = "serper"
    PERPLEXITY = "perplexity"
    GEMINI = "gemini"
    # Any OpenAI-compatible chat API whose model searches the web.
    CUSTOM = "custom"
