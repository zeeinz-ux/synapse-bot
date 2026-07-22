import asyncio
from typing import List, Dict

import aiohttp
import tenacity

from .base import AIProvider

GROQ_API_BASE = "https://api.groq.com/openai/v1"
GROQ_MODEL = "llama-3.3-70b-versatile"


def return_failure_tuple(retry_state):
    return "RETRY_LIMIT_EXCEEDED", False


class GroqProvider(AIProvider):
    name = "Groq"

    @tenacity.retry(
        wait=tenacity.wait_exponential(min=1, max=2),
        stop=tenacity.stop_after_attempt(2),
        retry=tenacity.retry_if_result(lambda res: res[1] is False),
        retry_error_callback=return_failure_tuple,
    )
    async def call(
        self,
        user_message: str,
        history: List[Dict],
        system_prompt: str,
        temperature: float = 0.75,
        images: list[dict] | None = None,
    ) -> tuple[str, bool]:
        if not self.api_key or not self.session:
            return "API_KEY_MISSING", False

        try:
            messages = [{"role": "system", "content": system_prompt}]
            for item in history:
                role = "assistant" if item["role"] == "assistant" else "user"
                messages.append({"role": role, "content": item["content"]})
            messages.append({"role": "user", "content": user_message})

            payload = {
                "model": GROQ_MODEL,
                "messages": messages,
                "temperature": temperature,
                "top_p": 0.95,
                "max_tokens": 8192,
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }

            url = f"{GROQ_API_BASE}/chat/completions"
            groq_timeout = aiohttp.ClientTimeout(total=10, connect=5)

            async with self.session.post(url, headers=headers, json=payload, timeout=groq_timeout) as resp:
                status = resp.status
                try:
                    data = await resp.json()
                except Exception:
                    data = {}

                if status == 429:
                    err_msg = data.get("error", {}).get("message", "Rate limit")
                    print(f"[AI CHAT] Groq Rate Limit (429): {err_msg[:100]}")
                    return "RATE_LIMIT", False

                if status in (401, 403):
                    print(f"[AI CHAT] Groq Auth Error ({status})")
                    return f"AUTH_{status}", False

                if status != 200:
                    print(f"[AI CHAT] Groq HTTP {status}")
                    return f"HTTP_{status}", False

                choices = data.get("choices", [])
                if not choices:
                    return "EMPTY_CHOICES", False

                return choices[0].get("message", {}).get("content", "").strip(), True

        except asyncio.TimeoutError:
            print("[AI CHAT] Groq Timeout (10s)")
            return "TIMEOUT", False
        except Exception as e:
            print(f"[AI CHAT] Groq Exception: {type(e).__name__}")
            return "EXCEPTION", False

    async def stream(
        self,
        user_message: str,
        history: List[Dict],
        system_prompt: str,
        temperature: float = 0.75,
        images: list[dict] | None = None,
    ):
        if not self.api_key or not self.session:
            yield ""
            return
        messages = [{"role": "system", "content": system_prompt}]
        for item in history:
            role = "assistant" if item["role"] == "assistant" else "user"
            messages.append({"role": role, "content": item["content"]})
        messages.append({"role": "user", "content": user_message})
        payload = {
            "model": GROQ_MODEL,
            "messages": messages,
            "temperature": temperature,
            "top_p": 0.95,
            "max_tokens": 8192,
            "stream": True,
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        url = f"{GROQ_API_BASE}/chat/completions"
        try:
            async with self.session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    yield ""
                    return
                async for line in resp.content:
                    if line:
                        decoded = line.decode(errors='replace').strip()
                        if decoded.startswith("data: ") and decoded != "data: [DONE]":
                            try:
                                import json
                                delta = json.loads(decoded[6:])["choices"][0].get("delta", {}).get("content", "")
                                if delta:
                                    yield delta
                            except Exception:
                                continue
        except Exception:
            yield ""
