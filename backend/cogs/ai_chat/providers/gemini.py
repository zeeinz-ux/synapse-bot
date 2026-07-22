import time
import asyncio
import base64
from datetime import datetime, timezone
from typing import List, Dict

import aiohttp
import tenacity

from .base import AIProvider

GOOGLE_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GOOGLE_MODEL = "gemini-3.6-flash"

GOOGLE_VISION_MODEL = "gemini-3.6-flash"
DAILY_QUOTA_LIMIT = 1500
QUOTA_RESERVE_THRESHOLD = 200
CIRCUIT_BREAKER_THRESHOLD = 3
CIRCUIT_BREAKER_COOLDOWN = 7200


def return_failure_tuple(retry_state):
    return "RETRY_LIMIT_EXCEEDED", False


class GeminiProvider(AIProvider):
    name = "Gemini"

    def __init__(self, session, api_key: str):
        super().__init__(session, api_key)
        self._gemini_circuit_open = False
        self._gemini_circuit_until = 0.0
        self._gemini_fail_streak = 0
        self._daily_count = 0
        self._daily_quota_date = datetime.now(timezone.utc).date()
        self._spam_cache: dict[str, tuple[float, bool]] = {}
        self._spam_cache_ttl = 300
        self._spam_last_check = 0.0
        self._spam_min_interval = 1.0

    # ── Quota ──

    def _check_daily_quota(self) -> bool:
        today = datetime.now(timezone.utc).date()
        if today != self._daily_quota_date:
            self._daily_count = 0
            self._daily_quota_date = today
        return self._daily_count < DAILY_QUOTA_LIMIT

    def quota_reserve_available(self) -> bool:
        self._check_daily_quota()
        return self._daily_count < (DAILY_QUOTA_LIMIT - QUOTA_RESERVE_THRESHOLD)

    @property
    def quota_available(self) -> bool:
        return self._check_daily_quota()

    @property
    def circuit_open(self) -> bool:
        return self._gemini_circuit_open

    @property
    def circuit_retry_after(self) -> float:
        return max(0.0, self._gemini_circuit_until - time.time())

    def reset_circuit(self):
        self._gemini_circuit_open = False
        self._gemini_fail_streak = 0

    def can_use_for_text(self) -> bool:
        return self.is_available and self.quota_available and self.quota_reserve_available()

    def can_use_for_vision(self) -> bool:
        return self.is_available and self.quota_available

    def record_success(self):
        self._gemini_fail_streak = 0
        self._daily_count += 1

    def record_failure(self):
        self._gemini_fail_streak += 1
        if self._gemini_fail_streak >= CIRCUIT_BREAKER_THRESHOLD:
            self._gemini_circuit_open = True
            self._gemini_circuit_until = time.time() + CIRCUIT_BREAKER_COOLDOWN

    # ── API call ──

    @tenacity.retry(
        wait=tenacity.wait_exponential(min=1, max=2),
        stop=tenacity.stop_after_attempt(1),
        retry=tenacity.retry_if_result(lambda res: res[1] is False),
        retry_error_callback=return_failure_tuple,
    )
    async def _call_google_gemini(
        self,
        user_message: str,
        history: List[Dict],
        system_prompt: str,
        temperature: float = 0.75,
        images: list[dict] | None = None,
    ) -> tuple[str, bool]:
        if not self.api_key or not self.session:
            return "API_KEY_MISSING", False

        has_images = bool(images)
        parts = [{"text": user_message}]
        if has_images:
            for img in images:
                parts.append({
                    "inline_data": {
                        "mime_type": img["mime_type"],
                        "data": img["data"],
                    }
                })

        contents = []
        for item in history:
            role = "model" if item["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": item["content"]}]})
        contents.append({"role": "user", "parts": parts})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "topP": 0.95,
                "maxOutputTokens": 8192,
            },
        }
        if not has_images:
            payload["system_instruction"] = {"parts": [{"text": system_prompt}]}
        else:
            parts[0]["text"] = f"{system_prompt}\n\n{user_message}"

        models_to_try = [GOOGLE_MODEL]
        if has_images:
            models_to_try = [GOOGLE_MODEL, GOOGLE_VISION_MODEL]

        last_status = 0
        for model in models_to_try:
            try:
                url = f"{GOOGLE_API_BASE}/models/{model}:generateContent?key={self.api_key}"
                if has_images:
                    print(f"[AI VISION] Trying model={model}, {len(images)} image(s)")

                vision_timeout = aiohttp.ClientTimeout(total=120, connect=30) if has_images else None
                async with self.session.post(
                    url, headers={"Content-Type": "application/json"}, json=payload, timeout=vision_timeout
                ) as resp:
                    status = resp.status
                    try:
                        data = await resp.json()
                    except Exception:
                        data = {}

                    if status == 429:
                        err_msg = data.get("error", {}).get("message", "Rate limit or quota exhausted.")
                        print(f"[AI CHAT] Google Rate Limit (429): {err_msg[:100]}")
                        return "RATE_LIMIT", False

                    if status == 503 and model != models_to_try[-1]:
                        print(f"[AI VISION] {model} returned 503, falling back to next model...")
                        last_status = status
                        continue

                    if status != 200:
                        print(f"[AI CHAT] Google HTTP {status} ({model})")
                        return f"HTTP_{status}", False

                    candidates = data.get("candidates", [])
                    if not candidates:
                        return "EMPTY_CANDIDATES", False

                    ret_parts = candidates[0].get("content", {}).get("parts", [])
                    if not ret_parts:
                        return "EMPTY_PARTS", False

                    return ret_parts[0].get("text", "").strip(), True

            except asyncio.TimeoutError:
                if model != models_to_try[-1]:
                    print(f"[AI VISION] {model} timed out, falling back to next model...")
                    continue
                print(f"[AI VISION] {model} timed out (last model)")
                return "TIMEOUT", False
            except Exception as e:
                if model != models_to_try[-1]:
                    print(f"[AI VISION] {model} error ({type(e).__name__}), falling back...")
                    continue
                print(f"[AI CHAT] Google Exception ({model}): {type(e).__name__}")
                return "EXCEPTION", False

        return f"HTTP_{last_status}", False

    async def call(
        self,
        user_message: str,
        history: List[Dict],
        system_prompt: str,
        temperature: float = 0.75,
        images: list[dict] | None = None,
        model: str | None = None,
    ) -> tuple[str, bool]:
        return await self._call_google_gemini(
            user_message, history, system_prompt, temperature, images
        )

    async def stream(
        self,
        user_message: str,
        history: List[Dict],
        system_prompt: str,
        temperature: float = 0.75,
        images: list[dict] | None = None,
        model: str | None = None,
    ):
        if not self.api_key or not self.session:
            yield ""
            return
        has_images = bool(images)
        parts = [{"text": user_message}]
        if has_images:
            for img in images:
                parts.append({"inline_data": {"mime_type": img["mime_type"], "data": img["data"]}})
        contents = []
        for item in history:
            role = "model" if item["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": item["content"]}]})
        contents.append({"role": "user", "parts": parts})
        payload = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "topP": 0.95, "maxOutputTokens": 8192},
        }
        if not has_images:
            payload["system_instruction"] = {"parts": [{"text": system_prompt}]}
        else:
            parts[0]["text"] = f"{system_prompt}\n\n{user_message}"
        use_model = model or GOOGLE_MODEL
        url = f"{GOOGLE_API_BASE}/models/{use_model}:streamGenerateContent?alt=sse&key={self.api_key}"
        try:
            async with self.session.post(url, headers={"Content-Type": "application/json"}, json=payload) as resp:
                if resp.status != 200:
                    yield ""
                    return
                async for line in resp.content:
                    if line:
                        try:
                            decoded = line.decode(errors='replace').strip()
                            if decoded.startswith("data: "):
                                import json
                                data = json.loads(decoded[6:])
                                candidates = data.get("candidates", [])
                                if candidates:
                                    text_parts = candidates[0].get("content", {}).get("parts", [])
                                    for p in text_parts:
                                        text = p.get("text", "")
                                        if text:
                                            yield text
                        except Exception:
                            continue
        except Exception:
            yield ""

    # ── Image spam analysis (Gemini Vision only) ──

    async def analyze_image_spam(self, image_data: bytes, mime_type: str = "image/png") -> bool:
        if not self.api_key or not self.session:
            return False
        if not self.quota_available:
            print("[AI VISION] Quota Gemini habis — image spam detection mati")
            return False

        try:
            b64 = base64.b64encode(image_data).decode()
            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Analisis gambar ini. Apakah mengandung: promosi judi/slot, scam, "
                                 "konten penipuan, atau phishing? Jawab HANYA 'YA' atau 'TIDAK'."},
                        {"inline_data": {"mime_type": mime_type, "data": b64}},
                    ]
                }],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 64},
            }

            url = f"{GOOGLE_API_BASE}/models/{GOOGLE_VISION_MODEL}:generateContent?key={self.api_key}"

            async with self.session.post(url, headers={"Content-Type": "application/json"}, json=payload) as resp:
                if resp.status != 200:
                    return False
                self._daily_count += 1
                data = await resp.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    return False
                text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                return "YA" in text.upper()
        except Exception as e:
            print(f"[AI VISION] Error: {e}")
            return False
