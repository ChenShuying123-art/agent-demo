"""LLM 调用模块（spec §7.8）。

职责边界：只负责"把 messages 交给模型、拿回文本"。
不负责组装提示词（prompts）、不负责检索（vectorstore）、也不负责编排（pipeline）。

坑 3（§4.2）：思考模式。
    百炼 qwen3.x 系列**默认开启思考模式**，会额外产生 reasoning token（更慢更贵），
    而且答案可能落在 `reasoning_content` 字段、导致 `content` 为空。
    RAG 问答不需要思考过程，所以必须显式传 `extra_body={"enable_thinking": False}`
    （由 settings.chat_enable_thinking 控制，默认 False）。

关于 temperature：§7.8 的签名写的是 `temperature=0.0`，这里改成 `None`，
    None 表示"用配置里的 chat_temperature"。这样 `.env` 里的 CHAT_TEMPERATURE 才真正生效，
    否则那个配置项会变成一个改了没反应的摆设。默认值仍是 0.0（§7.1 / NFR-4 要求可复现）。
"""

from __future__ import annotations

import logging
import time
from typing import Protocol, runtime_checkable

from openai import OpenAI

from kbqa.config import Settings
from kbqa.models import ChatResult, ToolCall

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """LLM 调用失败。

    `code` 保留百炼返回的错误码（例如 `invalid_api_key`），
    便于上层按 §8 的约定把 code 与 message 一起透传给前端排查（key / 额度 / 地域问题）。
    """

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


@runtime_checkable
class LLMProvider(Protocol):
    """对话模型接口（§7.8）。换实现只改这里，业务代码不动（NFR-2）。"""

    def chat(self, messages: list[dict], temperature: float | None = None) -> str:
        """传入 messages，返回模型生成的文本。"""
        ...

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float | None = None,
    ) -> ChatResult:
        """带工具 schema 调模型（spec-agent §19.6）。
        `tools=[]` 时的行为必须与 `chat()` 等价。
        """
        ...


class DashScopeChat:
    """百炼（DashScope）实现，走 OpenAI 兼容协议 compatible-mode/v1。"""

    def __init__(self, settings: Settings) -> None:
        # base_url 只到版本号，路径由 SDK 自己拼（§11：带上 /chat/completions 会 404）
        self._client = OpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.chat_base_url,
        )
        self._model = settings.chat_model
        self._enable_thinking = settings.chat_enable_thinking
        self._default_temperature = settings.chat_temperature

    def chat(self, messages: list[dict], temperature: float | None = None) -> str:
        """调用模型生成答案。

        Args:
            messages: OpenAI 风格的对话消息列表（system / user / assistant）。
            temperature: 采样温度；None 表示使用配置中的 chat_temperature。

        Returns:
            模型生成的文本（保证非空）。

        Raises:
            LLMError: 调用失败，或模型返回了空的 content。`code` 里带百炼的错误码。
        """
        temp = self._default_temperature if temperature is None else temperature
        started = time.perf_counter()

        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temp,
                # 必须显式关闭思考模式（§4.2 坑 3），否则 content 可能为空、答案跑到 reasoning_content
                extra_body={"enable_thinking": self._enable_thinking},
            )
        except Exception as exc:  # noqa: BLE001 —— 统一包装成带 code 的 LLMError 再抛出
            code = _error_code(exc)
            logger.error("LLM 调用失败 code=%s 模型=%s", code, self._model)
            raise LLMError(f"LLM 调用失败 code={code}：{exc}", code) from exc

        content = resp.choices[0].message.content
        if not content:
            # 走到这里通常是思考模式没关（或换成了会输出 reasoning 的模型）
            logger.error(
                "模型返回空 content（enable_thinking=%s 模型=%s）；请检查是否误开了思考模式",
                self._enable_thinking,
                self._model,
            )
            raise LLMError("模型返回空 content，可能是思考模式未关闭", "empty_content")

        logger.info(
            "生成完成 模型=%s 温度=%s 消息数=%d 答案长度=%d 耗时=%dms",
            self._model,
            temp,
            len(messages),
            len(content),
            int((time.perf_counter() - started) * 1000),
        )
        return content

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float | None = None,
    ) -> ChatResult:
        """带工具调用能力的对话（spec-agent §19.6）。

        Args:
            messages: OpenAI 风格消息列表；可包含 role="tool" 的历史结果。
            tools: OpenAI tools 格式的 schema 列表；空列表表示本轮不带工具。
            temperature: 采样温度；None 表示使用配置中的 chat_temperature。

        Returns:
            ChatResult：模型文本（可能为 None）、本次请求的工具调用、finish_reason。

        Raises:
            LLMError: 调用失败，或模型既没有给文本也没有请求工具。
                `code` 里带百炼的错误码，便于上层透传（§8）。
        """
        temp = self._default_temperature if temperature is None else temperature
        started = time.perf_counter()

        # tools=[] 时不传该字段：部分兼容实现会拒绝空数组；
        # 这样也保证与 chat() 的请求体完全一致（§19.6）。
        request: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": temp,
            # 工具调用叠加思考模式时 tool_calls 更易解析失败（§4.2 坑 3 的延伸）
            "extra_body": {"enable_thinking": self._enable_thinking},
        }
        if tools:
            request["tools"] = tools

        try:
            resp = self._client.chat.completions.create(**request)
        except Exception as exc:  # noqa: BLE001 —— 统一包装成带 code 的 LLMError
            code = _error_code(exc)
            logger.error(
                "LLM 工具调用失败 code=%s 模型=%s 工具数=%d",
                code,
                self._model,
                len(tools),
            )
            raise LLMError(f"LLM 工具调用失败 code={code}：{exc}", code) from exc

        choice = resp.choices[0]
        message = choice.message
        content = message.content or None
        tool_calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
            for tc in (message.tool_calls or [])
        ]
        finish_reason = choice.finish_reason or ""

        if content is None and not tool_calls:
            # 与 chat() 保持一致：空回答视为失败，避免上层拿到无法解释的结果
            logger.error(
                "模型既未返回 content 也未请求工具（finish_reason=%s 模型=%s）",
                finish_reason,
                self._model,
            )
            raise LLMError("模型未返回 content 且未请求工具", "empty_content")

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "工具调用完成 模型=%s 温度=%s 消息数=%d 带工具=%d finish_reason=%s "
            "答案长度=%d 工具调用数=%d 耗时=%dms",
            self._model,
            temp,
            len(messages),
            len(tools),
            finish_reason,
            len(content or ""),
            len(tool_calls),
            elapsed_ms,
        )
        # 参数是模型生成的 JSON 字符串，可能很长；按 §18.2 截断后再打日志
        for tc in tool_calls:
            logger.info("工具请求 name=%s 参数=%s", tc.name, _truncate(tc.arguments, 50))

        return ChatResult(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
        )


def _error_code(exc: Exception) -> str:
    """从 SDK 异常里尽量挖出百炼返回的错误码（§8 要求向上透传 code）。

    百炼的报错体有几种形状，这里都兜一下：
        {"error": {"code": "invalid_api_key", ...}}
        {"code": "InvalidParameter", ...}
    挖不到就退回 HTTP 状态码，保证异常信息里总有可排查的东西。
    """
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("code"):
            return str(error["code"])
        if body.get("code"):
            return str(body["code"])

    # openai SDK 有时把 JSON 报错体放在 message 字符串里，退一步再找一次
    text = str(exc)
    for marker in ('"code": "', "'code': '"):
        if marker in text:
            return text.split(marker, 1)[1].split('"', 1)[0].split("'", 1)[0]

    status = getattr(exc, "status_code", None)
    return str(status) if status is not None else "unknown"


def _truncate(text: str, limit: int = 50) -> str:
    """截断长文本，避免日志被模型参数/问题淹没（§18.2）。"""
    return text if len(text) <= limit else text[:limit] + "..."


def get_llm(settings: Settings) -> LLMProvider:
    """工厂函数：按配置返回对话模型实现（§7.8）。"""
    return DashScopeChat(settings)
