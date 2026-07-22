from typing import List, Dict

import aiohttp
import tenacity

from .base import AIProvider

COHERE_API_BASE = "https://api.cohere.com/v2"
COHERE_MODEL = "command-a-03-2025"


def return_failure_tuple(retry_state):
    return "RETRY_LIMIT_EXCEEDED", False


class CohereProvider(AIProvider):
    name = "Cohere"

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
                "model": COHERE_MODEL,
                "messages": messages,
                "temperature": temperature,
                "top_p": 0.95,
                "max_tokens": 8192,
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }

            url = f"{COHERE_API_BASE}/chat"

            async with self.session.post(url, headers=headers, json=payload) as resp:
                status = resp.status
                try:
                    data = await resp.json()
                except Exception:
                    data = {}

                if status == 429:
                    print("[AI CHAT] Cohere Rate Limit (429)")
                    return "RATE_LIMIT", False

                if status != 200:
                    print(f"[AI CHAT] Cohere HTTP {status}")
                    return f"HTTP_{status}", False

                msg = data.get("message", {})
                content_blocks = msg.get("content", [])
                if content_blocks:
                    return content_blocks[0].get("text", "").strip(), True
                return "EMPTY_RESPONSE", False

        except Exception as e:
            print(f"[AI CHAT] Cohere Exception: {type(e).__name__}")
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
            "model": COHERE_MODEL,
            "messages": messages,
            "temperature": temperature,
            "top_p": 0.95,
            "max_tokens": 8192,
            "stream": True,
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        url = f"{COHERE_API_BASE}/chat"
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
                                d = json.loads(decoded[6:])
                                text = d.get("text") or d.get("delta", {}).get("text") or d.get("content", {}).get("text", "")
                                if text:
                                    yield text
                            except Exception:
                                continue
        except Exception:
            yield ""
