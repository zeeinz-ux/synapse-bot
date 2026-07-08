import io
import json
import base64
import time
import os
from datetime import datetime, timezone
from typing import Optional

import aiohttp
from PIL import Image


class ImageSpamDetector:
    OCR_KEYWORDS = [
        "mrbeast", "cugamb", "usdt", "withdrawal success",
        "free crypto", "claim now", "free nitro",
        "steamcommunity", "discord-nitro", "login verify",
        "gift", "giveaway", "free-discord",
    ]

    def __init__(self):
        # ── Layer 1: Image rate limit ──
        self._user_image_times: dict[str, list[float]] = {}
        self.image_rate_max = 4
        self.image_rate_window = 10

        # ── Layer 2: Perceptual hashing ──
        self._known_spam_hashes: dict[int, float] = {}
        self._user_hashes: dict[str, list[int]] = {}
        self.hash_threshold = 6
        self.spam_hash_ttl = 604800
        self.dup_threshold = 3

        # ── Layer 2b: Duplicate within session ──
        self._session_img_count: dict[str, dict[int, int]] = {}

        # ── Layer 3: Vision result cache ──
        self._vision_cache: dict[int, tuple[float, bool]] = {}
        self.vision_cache_ttl = 600
        self._last_vision = 0.0
        self.vision_cooldown = 3.0
        self.max_vision_per_minute = 10
        self._vision_minute_count = 0
        self._vision_minute_start = 0.0

        # ── Layer 3b: OCR fallback (Google Cloud Vision API) ──
        self.vision_api_key = os.getenv("GOOGLE_VISION_API_KEY", "")
        self._last_ocr = 0.0
        self.ocr_cooldown = 5.0
        self.ocr_daily_max = 50
        self._ocr_today = 0
        self._ocr_date = datetime.now(timezone.utc).date()
        self.ocr_monthly_max = 900
        self._ocr_monthly_count = 0
        self._ocr_month = datetime.now(timezone.utc).strftime("%Y-%m")
        self._ocr_counter_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "data", "ocr_counter.json"
        )
        self._load_ocr_counters()

    # ── Layer 1: Rate limit ──

    def track_image_sent(self, user_id: str) -> bool:
        """Returns True if user exceeds image rate limit (after tracking this send)."""
        now = time.time()
        self._user_image_times.setdefault(user_id, [])
        self._user_image_times[user_id] = [
            t for t in self._user_image_times[user_id]
            if now - t < self.image_rate_window
        ]
        self._user_image_times[user_id].append(now)
        return len(self._user_image_times[user_id]) > self.image_rate_max

    def is_sending_images_fast(self, user_id: str) -> bool:
        """Read-only check: is user currently sending images rapidly?"""
        now = time.time()
        if user_id not in self._user_image_times:
            return False
        recent = [t for t in self._user_image_times[user_id] if now - t < self.image_rate_window]
        return len(recent) >= 2

    # ── Layer 2: Perceptual hash ──

    @staticmethod
    def compute_hash(image_data: bytes, hash_size: int = 8) -> Optional[int]:
        """Average perceptual hash. Returns None if image can't be opened."""
        try:
            img = Image.open(io.BytesIO(image_data))
            img = img.convert("L").resize((hash_size, hash_size), Image.LANCZOS)
            pixels = list(img.getdata())
            avg = sum(pixels) / len(pixels)
            return sum((1 << i) for i, p in enumerate(pixels) if p > avg)
        except Exception:
            return None

    @staticmethod
    def _hamming(h1: int, h2: int) -> int:
        return (h1 ^ h2).bit_count()

    def is_known_spam_hash(self, img_hash: int) -> bool:
        return any(
            self._hamming(img_hash, h) <= self.hash_threshold
            for h in self._known_spam_hashes
        )

    def flag_as_spam(self, img_hash: int) -> None:
        self._known_spam_hashes[img_hash] = time.time()

    def get_all_hashes(self) -> dict[int, float]:
        """Return {hash: timestamp} — for saving to Firestore."""
        return dict(self._known_spam_hashes)

    def load_hashes(self, hashes: dict[int, float]) -> None:
        """Load previously persisted hashes into memory."""
        self._known_spam_hashes.update(hashes)

    def get_expired_hashes(self) -> list[int]:
        """Return list of hash values that have exceeded TTL."""
        now = time.time()
        expired = [h for h, t in self._known_spam_hashes.items() if now - t >= self.spam_hash_ttl]
        for h in expired:
            self._known_spam_hashes.pop(h, None)
        return expired

    def count_duplicate(self, user_id: str, img_hash: int) -> int:
        """How many times this user sent a visually similar image."""
        self._session_img_count.setdefault(user_id, {})
        self._session_img_count[user_id][img_hash] = (
            self._session_img_count[user_id].get(img_hash, 0) + 1
        )
        return self._session_img_count[user_id][img_hash]

    # ── Layer 3: Vision API cache ──

    def get_vision_cache(self, img_hash: int) -> Optional[bool]:
        entry = self._vision_cache.get(img_hash)
        if entry and time.time() - entry[0] < self.vision_cache_ttl:
            return entry[1]
        return None

    def set_vision_cache(self, img_hash: int, is_spam: bool) -> None:
        self._vision_cache[img_hash] = (time.time(), is_spam)
        if len(self._vision_cache) > 500:
            cutoff = time.time() - self.vision_cache_ttl
            self._vision_cache = {k: v for k, v in self._vision_cache.items() if v[0] > cutoff}

    def can_call_vision(self) -> bool:
        now = time.time()
        if now - self._last_vision < self.vision_cooldown:
            return False
        # Reset counter every minute
        if now - self._vision_minute_start > 60:
            self._vision_minute_count = 0
            self._vision_minute_start = now
        if self._vision_minute_count >= self.max_vision_per_minute:
            return False
        self._last_vision = now
        self._vision_minute_count += 1
        return True

    # ── Image download ──

    async def download_image(self, url: str, session: aiohttp.ClientSession, max_bytes: int = 4 * 1024 * 1024) -> Optional[bytes]:
        """Download image from URL. Returns bytes or None."""
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                content_type = resp.headers.get("Content-Type", "")
                if not content_type.startswith("image/"):
                    return None
                data = await resp.read()
                if len(data) > max_bytes:
                    return None
                return data
        except Exception:
            return None

    # ── Layer 3b: OCR fallback via Google Cloud Vision API ──

    def can_ocr(self) -> bool:
        if not self.vision_api_key:
            return False
        now = time.time()
        if now - self._last_ocr < self.ocr_cooldown:
            return False
        today = datetime.now(timezone.utc).date()
        if today != self._ocr_date:
            self._ocr_today = 0
            self._ocr_date = today
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        if current_month != self._ocr_month:
            self._ocr_monthly_count = 0
            self._ocr_month = current_month
        if self._ocr_today >= self.ocr_daily_max:
            return False
        if self._ocr_monthly_count >= self.ocr_monthly_max:
            print(f"[OCR] Monthly limit reached ({self._ocr_monthly_count}), skipping")
            return False
        self._last_ocr = now
        self._ocr_today += 1
        self._ocr_monthly_count += 1
        self._save_ocr_counters()
        return True

    def _save_ocr_counters(self) -> None:
        data = {
            "month": self._ocr_month,
            "monthly_count": self._ocr_monthly_count,
            "date": str(self._ocr_date),
            "daily_count": self._ocr_today,
        }
        os.makedirs(os.path.dirname(self._ocr_counter_file), exist_ok=True)
        with open(self._ocr_counter_file, "w") as f:
            json.dump(data, f)

    def _load_ocr_counters(self) -> None:
        try:
            with open(self._ocr_counter_file) as f:
                data = json.load(f)
            now = datetime.now(timezone.utc)
            if data.get("month") == now.strftime("%Y-%m"):
                self._ocr_monthly_count = data.get("monthly_count", 0)
            if data.get("date") == str(now.date()):
                self._ocr_today = data.get("daily_count", 0)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    async def ocr_text_via_api(self, image_data: bytes, session: aiohttp.ClientSession) -> str:
        if not self.vision_api_key:
            return ""
        try:
            b64 = base64.b64encode(image_data).decode()
            payload = {
                "requests": [{
                    "image": {"content": b64},
                    "features": [{"type": "TEXT_DETECTION", "maxResults": 1}]
                }]
            }
            url = f"https://vision.googleapis.com/v1/images:annotate?key={self.vision_api_key}"
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return ""
                data = await resp.json()
                texts = data.get("responses", [{}])[0].get("textAnnotations", [])
                return texts[0]["description"].lower().strip() if texts else ""
        except Exception as e:
            print(f"[OCR] Error: {e}")
            return ""

    def is_ocr_spam(self, text: str) -> bool:
        return any(kw in text for kw in self.OCR_KEYWORDS)

    # ── Extract image URLs from message ──

    def extract_image_urls(self, message) -> list[tuple[str, str]]:
        """Return list of (url, mime_type) from attachments, embeds, and stickers."""
        urls: list[tuple[str, str]] = []

        for att in message.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                urls.append((att.url, att.content_type))

        for embed in message.embeds:
            if embed.image and embed.image.url:
                urls.append((embed.image.url, "image/png"))
            if embed.thumbnail and embed.thumbnail.url:
                urls.append((embed.thumbnail.url, "image/png"))

        for sticker in message.stickers:
            if sticker.url:
                urls.append((sticker.url, "image/png"))

        return urls
