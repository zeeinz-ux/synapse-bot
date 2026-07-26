import asyncio
from typing import List, Dict

import aiohttp

from .base import AIProvider

ZEN_API_BASE = "https://opencode.ai/zen/v1"

ZEN_FREE_MODELS = [
    "deepseek-v4-flash-free",
    "mimo-v2.5-free",
    "laguna-s-2.1-free",
    "ling-3.0-flash-free",
    "north-mini-code-free",
    "nemotron-3-ultra-free",
    "big-pickle",
]

ZEN_VISION_MODELS = [
    "deepseek-v4-flash-free",
    "nemotron-3-ultra-free",
]


class OpenCodeZenProvider(AIProvider):
    name = "OpenCode Zen"

    def __init__(self, session, api_key: str):
        super().__init__(session, api_key)
        self._free_models: list[str] = list(ZEN_FREE_MODELS)
        self._vision_models: list[str] = list(ZEN_VISION_MODELS)

    async def initialize(self):
        self._free_models, self._vision_models = await self._fetch_models()

    async def _fetch_models(self) -> tuple[list[str], list[str]]:
        if not self.api_key or not self.session:
            return list(ZEN_FREE_MODELS), list(ZEN_VISION_MODELS)

        try:
            url = f"{ZEN_API_BASE}/models"
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return list(ZEN_FREE_MODELS), list(ZEN_VISION_MODELS)

                data = await resp.json()
                free = []
                vision = []
                for m in data.get("data", []):
                    mid = m.get("id", "")
                    pricing = m.get("pricing") or {}
                    prompt_price = pricing.get("prompt")
                    completion_price = pricing.get("completion")
                    # Free = pricing kosong/null, atau prompt=0 dan completion=0
                    is_free = False
                    if not prompt_price and not completion_price:
                        is_free = True
                    elif str(prompt_price) == "0" and str(completion_price) == "0":
                        is_free = True
                    if not is_free:
                        continue
                    free.append(mid)
                    modality = (m.get("architecture") or {}).get("modality", "")
                    if self._supports_vision(modality, mid):
                        vision.append(mid)

                free.sort()
                vision.sort()

                if free:
                    print(f"[ZEN] {len(free)} free models loaded ({len(vision)} vision-capable)")
                    for m in free:
                        tag = " [VISION]" if m in vision else ""
                        print(f"[ZEN]   - {m}{tag}")
                    return free, vision

                print("[ZEN] Tidak ada free models dari API, pakai fallback.")
                return list(ZEN_FREE_MODELS), list(ZEN_VISION_MODELS)

        except Exception as e:
            print(f"[ZEN] Fetch error: {e}, pakai fallback.")
            return list(ZEN_FREE_MODELS), list(ZEN_VISION_MODELS)

    @staticmethod
    def _supports_vision(modality: str, model_id: str) -> bool:
        ml = modality.lower()
        if "vision" in ml or "image" in ml or "multimodal" in ml or "vl" in model_id.lower():
            return True
        return False

    async def _call_model(
        self,
        model: str,
        user_message: str,
        history: List[Dict],
        system_prompt: str,
        temperature: float,
        images: list[dict] | None = None,
    ) -> tuple[str, bool]:
        if not self.api_key or not self.session:
            return "API_KEY_MISSING", False

        try:
            messages = [{"role": "system", "content": system_prompt}]
            for item in history:
                role = "assistant" if item["role"] == "assistant" else "user"
                messages.append({"role": role, "content": item["content"]})

            if images:
                content_parts = [{"type": "text", "text": user_message}]
                for img in images:
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{img['mime_type']};base64,{img['data']}"
                        },
                    })
                messages.append({"role": "user", "content": content_parts})
            else:
                messages.append({"role": "user", "content": user_message})

            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "top_p": 0.95,
                "max_tokens": 8192,
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }

            url = f"{ZEN_API_BASE}/chat/completions"
            zen_timeout = aiohttp.ClientTimeout(total=30, connect=10)

            async with self.session.post(url, headers=headers, json=payload, timeout=zen_timeout) as resp:
                status = resp.status
                try:
                    data = await resp.json()
                except Exception:
                    data = {}

                if status == 429:
                    print(f"[ZEN] Rate Limit (429) on {model}")
                    return "RATE_LIMIT", False

                if status in (401, 403):
                    print(f"[ZEN] Auth Error ({status})")
                    return f"AUTH_{status}", False

                if status != 200:
                    print(f"[ZEN] HTTP {status} on {model}")
                    return f"HTTP_{status}", False

                choices = data.get("choices", [])
                if not choices:
                    print(f"[ZEN] Empty choices on {model}")
                    return "EMPTY_CHOICES", False

                return choices[0].get("message", {}).get("content", "").strip(), True

        except asyncio.TimeoutError:
            print(f"[ZEN] Timeout on {model}")
            return "TIMEOUT", False
        except Exception as e:
            print(f"[ZEN] Exception on {model}: {type(e).__name__}")
            return "EXCEPTION", False

    async def call(
        self,
        user_message: str,
        history: List[Dict],
        system_prompt: str,
        temperature: float = 0.75,
        images: list[dict] | None = None,
    ) -> tuple[str, bool]:
        if not self._free_models:
            self._free_models, self._vision_models = await self._fetch_models()

        has_images = bool(images)
        models_to_try = list(self._vision_models if has_images else self._free_models)

        for model in models_to_try:
            response, success = await self._call_model(
                model, user_message, history, system_prompt, temperature, images
            )
            if success:
                return response, True

        return "Semua model Zen free tier habis dicoba dan tidak ada yang berhasil.", False

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

        if not self._free_models:
            self._free_models, self._vision_models = await self._fetch_models()

        has_images = bool(images)
        models_to_try = list(self._vision_models if has_images else self._free_models)

        for model in models_to_try:
            messages = [{"role": "system", "content": system_prompt}]
            for item in history:
                role = "assistant" if item["role"] == "assistant" else "user"
                messages.append({"role": role, "content": item["content"]})

            if has_images:
                content_parts = [{"type": "text", "text": user_message}]
                for img in images:
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{img['mime_type']};base64,{img['data']}"},
                    })
                messages.append({"role": "user", "content": content_parts})
            else:
                messages.append({"role": "user", "content": user_message})

            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "top_p": 0.95,
                "max_tokens": 8192,
                "stream": True,
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }

            url = f"{ZEN_API_BASE}/chat/completions"
            try:
                async with self.session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 429:
                        continue
                    if resp.status != 200:
                        if model != models_to_try[-1]:
                            continue
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
                    return
            except Exception:
                if model != models_to_try[-1]:
                    continue
                yield ""
                return
        yield ""
