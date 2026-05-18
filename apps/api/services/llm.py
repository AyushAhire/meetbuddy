import json
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from config import settings

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text()


def get_llm(task: str = "extraction") -> BaseChatModel:
    """Return a LangChain chat model based on LLM_PROVIDER env var."""
    if settings.llm_provider == "openai":
        from langchain_openai import ChatOpenAI
        model = "gpt-4o-mini" if task == "extraction" else "gpt-4o"
        return ChatOpenAI(model=model, api_key=settings.openai_api_key)

    if settings.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        model = "claude-haiku-4-5-20251001" if task == "extraction" else "claude-sonnet-4-6"
        return ChatAnthropic(model=model, api_key=settings.anthropic_api_key)

    # Default: ollama
    from langchain_community.chat_models import ChatOllama
    return ChatOllama(model="mistral:latest", base_url=settings.ollama_base_url)


async def extract_insights(transcript: str) -> dict:
    """Call LLM to extract structured meeting insights."""
    prompt_template = _load_prompt("extract_insights.txt")
    prompt = prompt_template.replace("{transcript}", transcript)

    llm = get_llm(task="extraction")
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    raw = response.content.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import re
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError(f"LLM returned non-JSON: {raw[:200]}")


async def answer_query(question: str, context: str) -> str:
    """Call LLM to answer a query over meeting context."""
    prompt_template = _load_prompt("query_meetings.txt")
    prompt = prompt_template.replace("{context}", context).replace("{question}", question)

    llm = get_llm(task="query")
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    return response.content.strip()
