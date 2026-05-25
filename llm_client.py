"""qwen-plus 异步客户端封装，带重试和 JSON 容错解析"""
import asyncio
import json
import re

from openai import AsyncOpenAI

from config import (LLM_API_KEY, LLM_BASE_URL, LLM_MODEL,
                    LLM_TIMEOUT, LLM_MAX_RETRIES)

_client = AsyncOpenAI(
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL,
    timeout=LLM_TIMEOUT,
)


async def llm_call(prompt: str, system: str = None,
                   temperature: float = 0.7,
                   max_retries: int = LLM_MAX_RETRIES) -> str:
    """单次 LLM 调用，带重试"""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    last_err = None
    for attempt in range(max_retries + 1):
        try:
            resp = await _client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                temperature=temperature,
            )
            return resp.choices[0].message.content
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                await asyncio.sleep(2 ** attempt)
            continue
    raise last_err


def parse_json_loose(text: str) -> dict:
    """容错解析 LLM 返回的 JSON

    处理: ```json...``` 包裹、前后多余文字、中文引号
    """
    if not text:
        return {}

    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)

    # 提取第一个 { ... } 或 [ ... ] 块
    match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', text)
    if match:
        text = match.group(1)

    # 中文引号替换
    text = text.replace('\u201c', '"').replace('\u201d', '"')
    text = text.replace('\u2018', "'").replace('\u2019', "'")

    try:
        return json.loads(text)
    except json.JSONDecodeError as original_error:
        # 尝试修掉尾随逗号
        cleaned = re.sub(r',\s*([\}\]])', r'\1', text)
        try:
            return json.loads(cleaned)
        except Exception:
            print(f"[WARN] JSON 解析失败: {original_error}\n原文前 200 字: {text[:200]}")
            return {}
