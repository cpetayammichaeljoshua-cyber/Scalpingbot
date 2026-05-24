"""
LLM客户端封装
统一使用OpenAI格式调用
"""

import json
import re
import httpx
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config

# Default timeout for all LLM API calls (seconds).
# Without an explicit timeout, a hung upstream LLM endpoint will block a
# thread forever, exhausting the Flask thread pool under load.
_DEFAULT_TIMEOUT = httpx.Timeout(
    connect=15.0,   # TCP connection establishment
    read=120.0,     # Time to receive the complete response
    write=30.0,     # Time to send the request body
    pool=10.0,      # Time waiting for a connection from the pool
)


class LLMClient:
    """LLM客户端"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=_DEFAULT_TIMEOUT,
            max_retries=0,  # Retry logic is handled by retry_with_backoff decorators upstream
        )
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            response_format: 响应格式（如JSON模式）
            
        Returns:
            模型响应文本
        """
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if response_format:
            kwargs["response_format"] = response_format
        
        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        # 部分模型（如MiniMax M2.5）会在content中包含<think>思考内容，需要移除
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        return content
    
    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        发送聊天请求并返回JSON
        
        首先尝试使用模型原生的 JSON mode（response_format={"type":"json_object"}）。
        若模型不支持该参数（HTTP 400），则回退到普通模式并手动解析 JSON。
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            解析后的JSON对象
        """
        # Try native JSON mode first
        try:
            response = self.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"}
            )
        except Exception as e:
            # Some models / providers don't support response_format — fall back
            # to a plain text call and parse the JSON ourselves.
            err_str = str(e).lower()
            if "response_format" in err_str or "400" in err_str or "unsupported" in err_str:
                response = self.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=None
                )
            else:
                raise

        # 清理markdown代码块标记
        cleaned = response.strip()
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)
        cleaned = cleaned.strip()

        # If the model returned an empty string, raise clearly
        if not cleaned:
            raise ValueError("LLM返回了空响应，无法解析JSON")

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM返回的JSON格式无效: {cleaned}") from exc
