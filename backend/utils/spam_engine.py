import re
import time
from urllib.parse import urlparse
from datetime import datetime, timezone


class SpamEngine:
    def __init__(self):
        self.url_patterns = [
            r"https?://(bit\.ly|t\.co|tinyurl\.com|shorturl\.at|rb\.gy|cutt\.ly|ow\.ly|buff\.ly)",
            r"discord(?:\.gg|\.com/invite)/[a-zA-Z0-9_\-]+",
        ]
        self.compiled_url_patterns = [re.compile(p, re.IGNORECASE) for p in self.url_patterns]
        self._url_extractor = re.compile(r"https?://[^\s/\"'<>]+", re.IGNORECASE)

        self.keywords = [
            "slot", "judi", "deposit", "gacor", "maxwin",
            "join now", "click here", "free crypto", "giveaway", "free nitro",
        ]

        self.suspicious_domain_keywords = [
            "free-nitro", "nitro-gift", "discord-nitro", "discordgift", "steamdiscord",
            "steamcommunity.com/login", "steamcommunitiy", "steamcomnunity",
            "free-discord", "free-steam",
            "account-verification", "account-verify", "login-verify",
            "giveaway-win", "you-won", "you-win",
            "nitro-free", "discord-free", "verify-account", "verify-login",
            "get-free", "claim-free", "claim-nitro", "free-nitro",
            "discord-nitro-free", "nitro-steam", "free-discord-nitro",
        ]

        self.suspicious_tlds = {
            ".xyz", ".top", ".gq", ".cf", ".ml", ".ga", ".tk", ".pw", ".cc",
        }

        self.known_targets = [
            "discord", "steam", "netflix", "spotify", "youtube", "google",
            "instagram", "facebook", "twitter", "github", "paypal",
            "amazon", "apple", "microsoft", "roblox",
        ]

        self.homoglyph_map = {
            "0": "o", "1": "i", "3": "e", "4": "a", "5": "s",
            "6": "g", "7": "t", "8": "b", "9": "g",
            "а": "a", "е": "e", "о": "o", "с": "c",
            "у": "u", "х": "x", "і": "i", "ј": "j",
            "к": "k", "м": "m", "н": "h", "р": "p",
            "т": "t", "в": "b", "ѕ": "s", "д": "d",
            "п": "p", "з": "z", "и": "i", "л": "l",
        }

        self._msg_timestamps: dict[str, list[float]] = {}
        self._msg_contents: dict[str, list[tuple[float, str]]] = {}

    def _normalize(self, text: str) -> str:
        text = text.lower()
        for c, r in self.homoglyph_map.items():
            text = text.replace(c, r)
        text = re.sub(r"[-._/]", " ", text)
        text = re.sub(r"[^a-z0-9\s]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _has_keyword(self, text: str) -> bool:
        normalized = self._normalize(text)
        compact = re.sub(r"\s+", "", normalized)
        return any(kw in normalized or kw in compact for kw in self.keywords)

    def _has_suspicious_url(self, text: str) -> bool:
        return any(p.search(text) for p in self.compiled_url_patterns)

    def _extract_urls(self, text: str) -> list[str]:
        return self._url_extractor.findall(text)

    def _get_domain(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            return parsed.hostname or ""
        except Exception:
            return ""

    def _get_tld(self, domain: str) -> str:
        try:
            parts = domain.rsplit(".", 1)
            if len(parts) == 2:
                return "." + parts[-1]
        except Exception:
            pass
        return ""

    def _has_suspicious_domain(self, urls: list[str]) -> bool:
        for url in urls:
            url_lower = url.lower()
            for pattern in self.suspicious_domain_keywords:
                if pattern in url_lower:
                    return True
        return False

    def _has_suspicious_tld(self, urls: list[str]) -> bool:
        for url in urls:
            domain = self._get_domain(url)
            if domain and self._get_tld(domain) in self.suspicious_tlds:
                return True
        return False

    def _is_typosquat(self, urls: list[str]) -> bool:
        for url in urls:
            domain = self._get_domain(url)
            if not domain:
                continue
            normalized = self._normalize(domain)
            for target in self.known_targets:
                if target in normalized and target not in domain:
                    return True
        return False

    def _extract_text(self, message) -> str:
        texts = [message.content or ""]
        for embed in message.embeds:
            if embed.url:
                texts.append(embed.url)
            if embed.title:
                texts.append(embed.title)
            if embed.description:
                texts.append(embed.description)
            for field in embed.fields:
                if field.name:
                    texts.append(field.name)
                if field.value:
                    texts.append(field.value)
            if embed.author and embed.author.name:
                texts.append(embed.author.name)
            if embed.footer and embed.footer.text:
                texts.append(embed.footer.text)
        for att in message.attachments:
            if att.filename:
                texts.append(att.filename)
        return " ".join(texts)

    def track_message(self, message) -> None:
        user_id = str(message.author.id)
        content = message.content
        now = time.time()

        self._msg_timestamps.setdefault(user_id, [])
        self._msg_timestamps[user_id] = [
            t for t in self._msg_timestamps[user_id] if now - t < 10
        ]
        self._msg_timestamps[user_id].append(now)

        self._msg_contents.setdefault(user_id, [])
        self._msg_contents[user_id] = [
            (t, c) for t, c in self._msg_contents[user_id] if now - t < 30
        ]
        self._msg_contents[user_id].append((now, content))

    def is_rate_flooding(self, user_id: str, max_msgs: int = 5) -> bool:
        now = time.time()
        if user_id not in self._msg_timestamps:
            return False
        recent = [t for t in self._msg_timestamps[user_id] if now - t < 10]
        return len(recent) > max_msgs

    def is_duplicate_spam(self, user_id: str, content: str, threshold: int = 3) -> bool:
        now = time.time()
        if user_id not in self._msg_contents:
            return False
        recent = [(t, c) for t, c in self._msg_contents[user_id] if now - t < 30]
        return sum(1 for _, c in recent if c == content) >= threshold

    def get_risk_score(self, message) -> int:
        if hasattr(message.author, "guild_permissions") and message.author.guild_permissions.manage_messages:
            return 0

        score = 0
        content = message.content or ""
        all_text = self._extract_text(message)
        urls = self._extract_urls(all_text)

        if hasattr(message, "mention_everyone") and message.mention_everyone:
            score += 5
        elif re.search(r"@(everyone|here)", content, re.IGNORECASE):
            score += 5

        if self._has_suspicious_url(all_text):
            score += 5

        if urls:
            if self._has_suspicious_domain(urls):
                score += 5
            if self._is_typosquat(urls):
                score += 5
            if self._has_suspicious_tld(urls) and hasattr(message.author, "created_at"):
                account_age = (datetime.now(timezone.utc) - message.author.created_at).days
                if account_age < 7:
                    score += 5

        if self._has_keyword(all_text):
            score += 5

        if hasattr(message.author, "created_at"):
            account_age = (datetime.now(timezone.utc) - message.author.created_at).days
            if account_age < 1:
                score += 5
            elif account_age < 60:
                score += 5

        if hasattr(message.author, "joined_at") and message.author.joined_at:
            join_seconds = (datetime.now(timezone.utc) - message.author.joined_at).total_seconds()
            if join_seconds < 3600:
                score += 5
            elif join_seconds < 86400:
                score += 3
            elif join_seconds < 604800:
                score += 2

        user_id = str(message.author.id)
        if self.is_rate_flooding(user_id):
            score += 5
        if self.is_duplicate_spam(user_id, content):
            score += 5

        return score

    def is_spam_heuristic(self, message) -> bool:
        return self.get_risk_score(message) >= 5

    def is_new_account(self, message) -> bool:
        if hasattr(message.author, "created_at"):
            account_age = (datetime.now(timezone.utc) - message.author.created_at).days
            return account_age < 1
        return False
