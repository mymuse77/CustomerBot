"""DeepSeek LLM 客户端"""

import httpx
from typing import Optional

from app.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL


class LLMClient:
    """DeepSeek API 客户端"""

    def __init__(self):
        self.api_key = DEEPSEEK_API_KEY
        self.base_url = DEEPSEEK_BASE_URL
        self.model = DEEPSEEK_MODEL
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        user_message: str,
        system_message: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        """
        调用 DeepSeek Chat API。

        参数:
            user_message: 用户消息
            system_message: 系统提示词
            temperature: 生成温度（Text2SQL 用低温度保证稳定性）
            max_tokens: 最大生成 token 数

        返回:
            LLM 生成的文本
        """
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()

    async def generate_sql(self, question: str, system_prompt: str) -> str:
        """
        生成 SQL 查询语句。使用低温度确保稳定输出。
        """
        sql = await self.chat(
            user_message=question,
            system_message=system_prompt,
            temperature=0.0,
            max_tokens=1024,
        )
        # 清理可能存在的 markdown 代码块标记
        sql = sql.strip()
        if sql.startswith("```sql"):
            sql = sql[6:]
        if sql.startswith("```"):
            sql = sql[3:]
        if sql.endswith("```"):
            sql = sql[:-3]
        return sql.strip()

    async def generate_answer(
        self, question: str, system_prompt: str, result_text: str
    ) -> str:
        """
        根据查询结果生成自然语言回答。使用稍高温度让回答更自然。
        """
        return await self.chat(
            user_message=result_text,
            system_message=system_prompt,
            temperature=0.7,
            max_tokens=2048,
        )


# 全局单例
llm_client = LLMClient()
