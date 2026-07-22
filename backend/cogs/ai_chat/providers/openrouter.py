import asyncio
from typing import List, Dict

import aiohttp

from .base import AIProvider

OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_PAID_FALLBACK = "meta-llama/llama-3.3-70b-instruct"
OPENROUTER_SAFETY_MODEL = "nvidia/nemotron-3.5-content-safety:free"

OPENROUTER_FALLBACK_MODELS = [
    "openrouter/free",
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "nvidia/nemotron-nano-9b-v2:free",
    "poolside/laguna-s-2.1:free",
    "poolside/laguna-m.1:free",
    "google/lyria-3-pro-preview",
]


def _supports_vision(modality: str, model_id: str) -> bool:
    ml = modality.lower()
    if "vision" in ml or "image" in ml or "multimodal" in ml or "vl" in model_id.lower():
        return True
    return False


def _is_chat_model(modality: str) -> bool:
    ml = modality.lower()
    # Lyria dan model serupa generate audio, bukan chat text
    if "audio" in ml and "text+image->text+audio" in ml:
        return False
    return True


class OpenRouterProvider(AIProvider):
    name = "OpenRouter"

    def __init__(self, session, api_key: str):
        super().__init__(session, api_key)
        self._free_models: list[str] = []
        self._vision_models: list[str] = []

    async def initialize(self):
        self._free_models, self._vision_models = await self._fetch_models()

    async def _fetch_models(self) -> tuple[list[str], list[str]]:
        if not self.session:
            fb = list(OPENROUTER_FALLBACK_MODELS)
            return fb, [m for m in fb if _supports_vision("", m)]

        try:
            url = f"{OPENROUTER_API_BASE}/models"
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    print("[OPENROUTER] Gagal fetch model list, pakai fallback.")
                    fb = list(OPENROUTER_FALLBACK_MODELS)
                    return fb, [m for m in fb if _supports_vision("", m)]

                data = await resp.json()
                free = []
                vision = []
                for m in data.get("data", []):
                    p = m.get("pricing", {})
                    if p.get("prompt") != "0" or p.get("completion") != "0":
                        continue
                    mid = m["id"]
                    modality = m.get("architecture", {}).get("modality", "")
                    if not _is_chat_model(modality):
                        continue
                    free.append(mid)
                    if _supports_vision(modality, mid):
                        vision.append(mid)

                free.sort()
                vision.sort()

                if free:
                    print(f"[OPENROUTER] {len(free)} free models loaded ({len(vision)} vision-capable)")
                    for m in free:
                        tag = " [VISION]" if m in vision else ""
                        print(f"[OPENROUTER]   - {m}{tag}")
                    return free, vision

                print("[OPENROUTER] Tidak ada free models dari API, pakai fallback.")
                fb = list(OPENROUTER_FALLBACK_MODELS)
                return fb, [m for m in fb if _supports_vision("", m)]

        except Exception as e:
            print(f"[OPENROUTER] Fetch error: {e}, pakai fallback.")
            fb = list(OPENROUTER_FALLBACK_MODELS)
            return fb, [m for m in fb if _supports_vision("", m)]

    async def _call_openrouter_model(
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

            url = f"{OPENROUTER_API_BASE}/chat/completions"
            or_timeout = aiohttp.ClientTimeout(total=30, connect=10)

            async with self.session.post(url, headers=headers, json=payload, timeout=or_timeout) as resp:
                status = resp.status
                try:
                    data = await resp.json()
                except Exception:
                    data = {}

                if status == 429:
                    print(f"[OPENROUTER] Rate Limit (429) on {model}")
                    return "RATE_LIMIT", False

                if status in (401, 403):
                    print(f"[OPENROUTER] Auth Error ({status})")
                    return f"AUTH_{status}", False

                if status != 200:
                    print(f"[OPENROUTER] HTTP {status} on {model}")
                    return f"HTTP_{status}", False

                choices = data.get("choices", [])
                if not choices:
                    print(f"[OPENROUTER] Empty choices on {model}")
                    return "EMPTY_CHOICES", False

                return choices[0].get("message", {}).get("content", "").strip(), True

        except asyncio.TimeoutError:
            print(f"[OPENROUTER] Timeout on {model}")
            return "TIMEOUT", False
        except Exception as e:
            print(f"[OPENROUTER] Exception on {model}: {type(e).__name__}")
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
            response, success = await self._call_openrouter_model(
                model, user_message, history, system_prompt, temperature, images
            )
            if success:
                return response, True

        response, success = await self._call_openrouter_model(
            OPENROUTER_PAID_FALLBACK, user_message, history, system_prompt, temperature, images
        )
        if success:
            return response, True

        return response, False

    async def check_content_safety(self, text: str, image_data: bytes | None = None, mime_type: str = "image/png") -> tuple[bool, str]:
        """
        Cek apakah konten aman menggunakan Nemotron 3.5 Content Safety.
        Returns (is_safe, reason).
        """
        if not self.api_key or not self.session:
            return True, "API tidak tersedia"

        try:
            content_parts = [{"type": "text", "text": text}]
            if image_data:
                import base64
                b64 = base64.b64encode(image_data).decode()
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                })

            payload = {
                "model": OPENROUTER_SAFETY_MODEL,
                "messages": [{"role": "user", "content": content_parts if image_data else text}],
                "temperature": 0.1,
                "max_tokens": 64,
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }

            url = f"{OPENROUTER_API_BASE}/chat/completions"
            async with self.session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return True, "API error"
                data = await resp.json()
                choices = data.get("choices", [])
                if not choices:
                    return True, "empty response"
                msg = choices[0].get("message", {})
                content = (msg.get("content") or "").strip()
                reasoning = (msg.get("reasoning") or "").strip()
                verdict_text = reasoning or content

                if "unsafe" in verdict_text.lower():
                    return False, verdict_text
                if not verdict_text:
                    return True, "no verdict (safe assumed)"
                return True, verdict_text

        except Exception as e:
            print(f"[OPENROUTER SAFETY] Error: {e}")
            return True, "error fallback to safe"

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
        if not models_to_try:
            models_to_try = [OPENROUTER_PAID_FALLBACK]
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
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
            url = f"{OPENROUTER_API_BASE}/chat/completions"
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
