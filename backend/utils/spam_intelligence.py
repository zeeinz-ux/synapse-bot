import hashlib
import json
import time
import asyncio
import re
from datetime import datetime, timezone
from typing import Optional

from backend.cogs.database.firebase_setup import db

THREAT_COLLECTION = "scam_signatures"


class SpamIntelligence:
    def __init__(self, bot):
        self.bot = bot
        self._threat_cache: dict[str, dict] = {}
        self._cache_loaded = False
        self._ban_patterns_cache: dict[str, dict] = {}
        self._ban_patterns_loaded = False

    async def ensure_cache_loaded(self):
        if self._cache_loaded:
            return
        await self._load_threat_signatures()
        await self._load_ban_patterns()
        self._cache_loaded = True
        self._ban_patterns_loaded = True

    async def _load_threat_signatures(self):
        if db is None:
            return
        try:
            docs = await asyncio.to_thread(
                lambda: list(db.collection(THREAT_COLLECTION).stream())
            )
            count = 0
            for doc in docs:
                data = doc.to_dict()
                if data:
                    key = str(data.get("imageHash", doc.id))
                    self._threat_cache[key] = data
                    count += 1
            print(f"[SPAM INTEL] Loaded {count} threat signatures from Firestore")
        except Exception as e:
            print(f"[SPAM INTEL] Failed to load threat signatures: {e}")

    async def analyze(
        self,
        content: str = "",
        image_data: Optional[bytes] = None,
        mime_type: Optional[str] = None,
        author_id: Optional[str] = None,
        account_age_days: int = 999,
        join_age_days: int = 999,
        mention_everyone: bool = False,
        has_attachments: bool = False,
        has_embeds: bool = False,
        matched_keywords: Optional[list] = None,
        heuristic_score: int = 0,
        img_hash: Optional[int] = None,
        guild_id: Optional[str] = None,
        channel_id: Optional[str] = None,
    ) -> dict:
        result = {
            "classification": "safe",
            "confidence": 0,
            "riskLevel": "safe",
            "threatCategory": "",
            "recommendation": "IGNORE",
            "reasoning": [],
            "detectedIndicators": [],
            "shouldStoreSignature": False,
            "signatureExists": False,
            "firestoreAction": "",
            "falsePositiveRisk": "low",
            "explanation": "",
            "domains": [],
            "walletAddresses": {},
            "logos": [],
        }

        matched_keywords = matched_keywords or []

        # Step 1: Check known threat signature by image hash
        if img_hash is not None:
            known = await self._find_matching_threat(img_hash, guild_id, channel_id, author_id)
            if known is not None:
                result.update({
                    "classification": "confirmed_scam",
                    "confidence": max(known.get("confidence", 85), 90),
                    "riskLevel": "critical",
                    "threatCategory": known.get("category", "known_scam"),
                    "recommendation": "AUTO_BAN",
                    "signatureExists": True,
                    "falsePositiveRisk": "very_low",
                    "reasoning": [f"Image matches known {known.get('category', 'scam')} threat signature"],
                    "explanation": f"Known scam campaign: {known.get('category', 'unknown')}",
                })
                return result

        # Step 2: Extract indicators
        indicators = self._extract_indicators(
            content=content,
            heuristic_score=heuristic_score,
            account_age_days=account_age_days,
            join_age_days=join_age_days,
            mention_everyone=mention_everyone,
            has_attachments=has_attachments,
            has_embeds=has_embeds,
            matched_keywords=matched_keywords,
        )
        result["detectedIndicators"] = indicators

        # Step 3: Run Vision AI if image present
        vision_indicators = []
        ocr_text = ""
        if image_data and mime_type:
            vision_result = await self._analyze_with_vision(image_data, mime_type, content)
            if vision_result.get("isScam"):
                vision_indicators = vision_result.get("detectedIndicators", [])
                result["detectedIndicators"].extend(vision_indicators)
                if vision_result.get("reasoning"):
                    result["reasoning"].extend(vision_result["reasoning"])
                ocr_text = vision_result.get("ocrText", "")

        # Step 4: Extract domains, wallet addresses, and logos
        result["domains"] = self._extract_domains(content, ocr_text)
        result["walletAddresses"] = self._extract_wallet_addresses(content, ocr_text)
        result["logos"] = self._extract_logos(content, ocr_text)

        # Step 5: Compute confidence
        confidence = self._compute_confidence(
            indicators=result["detectedIndicators"],
            heuristic_score=heuristic_score,
            account_age_days=account_age_days,
            join_age_days=join_age_days,
            has_image=image_data is not None,
            vision_indicators=vision_indicators,
            has_ocr_text=bool(ocr_text),
        )
        result["confidence"] = confidence

        # Step 5: Assess false positive risk
        fp_risk = self._assess_false_positive_risk(
            indicators=result["detectedIndicators"],
            confidence=confidence,
            account_age_days=account_age_days,
            has_image=image_data is not None,
        )
        result["falsePositiveRisk"] = fp_risk

        # Step 6: Classification and risk level
        if confidence >= 85 and len(result["detectedIndicators"]) >= 3:
            result["classification"] = "confirmed_scam"
            result["riskLevel"] = "critical"
        elif confidence >= 61:
            result["classification"] = "suspicious"
            result["riskLevel"] = "high"
        elif confidence >= 41:
            result["classification"] = "suspicious"
            result["riskLevel"] = "medium"
        elif confidence >= 21:
            result["classification"] = "low_risk"
            result["riskLevel"] = "low"
        else:
            result["classification"] = "safe"
            result["riskLevel"] = "safe"

        # Step 7: Threat category
        if result["classification"] != "safe":
            result["threatCategory"] = self._classify_threat(
                indicators=result["detectedIndicators"],
                content=content,
            )

        # Step 8: Recommendation
        result["recommendation"] = self._get_recommendation(
            classification=result["classification"],
            confidence=confidence,
            falsePositiveRisk=fp_risk,
            is_known_threat=result["signatureExists"],
            indicators=result["detectedIndicators"],
            has_image=image_data is not None,
        )

        # Step 9: Store signature decision
        if confidence >= 85 and len(result["detectedIndicators"]) >= 3 and image_data:
            result["shouldStoreSignature"] = True
            result["firestoreAction"] = "STORE_SIGNATURE"

        # Step 10: Explanation
        if result["classification"] != "safe":
            result["explanation"] = self._generate_explanation(result, content)

        return result

    def _extract_indicators(
        self,
        content: str,
        heuristic_score: int,
        account_age_days: int,
        join_age_days: int,
        mention_everyone: bool,
        has_attachments: bool,
        has_embeds: bool,
        matched_keywords: list,
    ) -> list:
        indicators = []
        text_lower = content.lower()

        if heuristic_score >= 10:
            indicators.append("high_heuristic_score")
        elif heuristic_score >= 5:
            indicators.append("elevated_heuristic_score")

        if mention_everyone:
            indicators.append("everyone_mention")

        if heuristic_score >= 5 and self._has_url(text_lower):
            indicators.append("content_with_url")

        if matched_keywords:
            indicators.append("keyword_match")

        if account_age_days < 1:
            indicators.append("new_account")
        elif account_age_days < 60:
            indicators.append("young_account")

        if join_age_days < 1:
            indicators.append("fresh_join")
        elif join_age_days < 7:
            indicators.append("recent_join")

        if "discord.gg/" in text_lower or "discord.com/invite/" in text_lower:
            indicators.append("discord_invite")

        crypto_terms = ["usdt", "bitcoin", "ethereum", "crypto", "withdrawal", "invest", "profit", "wallet", "bnb", "solana", "eth"]
        if any(t in text_lower for t in crypto_terms):
            indicators.append("crypto_terminology")

        giveaway_terms = ["giveaway", "free nitro", "claim now", "you won", "you are winner", "congratulations you won", "prize", "mrbeast", "elon musk"]
        if any(t in text_lower for t in giveaway_terms):
            indicators.append("giveaway_terminology")

        if has_attachments and heuristic_score >= 5:
            indicators.append("attachment_with_risk")

        return indicators

    def _has_url(self, text: str) -> bool:
        return bool(re.search(r"https?://[^\s/\"'<>]+", text, re.IGNORECASE))

    def _extract_domains(self, *texts: str) -> list:
        domains = set()
        url_pattern = re.compile(r"https?://([^\s/\"'<>]+)", re.IGNORECASE)
        safe_domains = {"discord.com", "discord.gg", "discordapp.com", "google.com", "youtube.com",
                        "github.com", "twitter.com", "x.com", "instagram.com", "facebook.com",
                        "tenor.com", "giphy.com", "cdn.discordapp.com", "media.discordapp.net"}
        for text in texts:
            if not text:
                continue
            for match in url_pattern.finditer(text):
                domain = match.group(1).lower()
                domain = domain.split("@")[-1].split(":")[0].lstrip("www.")
                if domain and domain not in safe_domains:
                    domains.add(domain)
        return sorted(domains)

    def _extract_wallet_addresses(self, *texts: str) -> dict:
        addresses = {"btc": [], "eth": [], "sol": [], "trx": [], "other": []}
        seen = set()
        for text in texts:
            if not text:
                continue
            for match in re.finditer(r"0x[a-fA-F0-9]{40}", text):
                addr = match.group()
                if addr not in seen:
                    seen.add(addr)
                    addresses["eth"].append(addr)
            for match in re.finditer(r"\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b", text):
                addr = match.group()
                if addr not in seen and not re.match(r"0x", addr):
                    seen.add(addr)
                    addresses["btc"].append(addr)
            for match in re.finditer(r"\bbc1[a-zA-HJ-NP-Z0-9]{39,59}\b", text):
                addr = match.group()
                if addr not in seen:
                    seen.add(addr)
                    addresses["btc"].append(addr)
            for match in re.finditer(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b", text):
                addr = match.group()
                if addr not in seen and not re.match(r"[13bc0xT]", addr) and not re.match(r"^[a-z0-9\-]+\.[a-z]{2,}", addr):
                    seen.add(addr)
                    addresses["sol"].append(addr)
            for match in re.finditer(r"\bT[a-zA-HJ-NP-Z0-9]{33}\b", text):
                addr = match.group()
                if addr not in seen:
                    seen.add(addr)
                    addresses["trx"].append(addr)
        return {k: v for k, v in addresses.items() if v}

    def _extract_logos(self, *texts: str) -> list:
        logos = set()
        brand_map = {
            "binance": "Binance", "bybit": "Bybit", "okx": "OKX", "coinbase": "Coinbase",
            "kucoin": "KuCoin", "huobi": "Huobi", "crypto.com": "Crypto.com",
            "metamask": "MetaMask", "trustwallet": "TrustWallet", "phantom": "Phantom",
            "telegram": "Telegram", "whatsapp": "WhatsApp", "discord": "Discord",
        }
        combined = " ".join(t.lower() for t in texts if t)
        for key, name in brand_map.items():
            if key in combined:
                logos.add(name)
        return sorted(logos)

    async def _find_matching_threat(self, img_hash: int, guild_id: Optional[str] = None, channel_id: Optional[str] = None, user_id: Optional[str] = None) -> Optional[dict]:
        cache_key = str(img_hash)
        if cache_key in self._threat_cache:
            sig = self._threat_cache[cache_key]
            asyncio.create_task(self._increment_detection(sig.get("id", cache_key), guild_id, channel_id, user_id))
            return sig

        for cached_hash_str, sig in self._threat_cache.items():
            try:
                cached_hash = int(cached_hash_str)
                hamming = (img_hash ^ cached_hash).bit_count()
                if hamming <= 6:
                    asyncio.create_task(self._increment_detection(sig.get("id", cached_hash_str), guild_id, channel_id, user_id))
                    return sig
            except (ValueError, TypeError):
                continue

        return None

    async def _increment_detection(self, sig_id: str, guild_id: Optional[str] = None, channel_id: Optional[str] = None, user_id: Optional[str] = None):
        if db is None:
            return
        try:
            doc_ref = db.collection(THREAT_COLLECTION).document(sig_id)
            doc = await asyncio.to_thread(doc_ref.get)
            current = doc.to_dict().get("timesDetected", 0) if doc.exists else 0
            update = {"timesDetected": current + 1, "lastSeen": time.time()}
            if guild_id:
                update["lastSeenGuild"] = guild_id
            if channel_id:
                update["lastSeenChannel"] = channel_id
            if user_id:
                update["lastSeenUser"] = user_id
            await asyncio.to_thread(doc_ref.update, update)
        except Exception:
            pass

    async def _analyze_with_vision(self, image_data: bytes, mime_type: str, text_context: str) -> dict:
        ai_cog = self.bot.get_cog("AIChat")
        if not ai_cog:
            return {"isScam": False, "detectedIndicators": [], "reasoning": [], "ocrText": ""}
        return await ai_cog.analyze_image_spam_intelligence(image_data, mime_type, text_context)

    def _compute_confidence(
        self,
        indicators: list,
        heuristic_score: int,
        account_age_days: int,
        join_age_days: int,
        has_image: bool,
        vision_indicators: list,
        has_ocr_text: bool,
    ) -> int:
        score = 0

        if heuristic_score >= 10:
            score += 30
        elif heuristic_score >= 5:
            score += 20
        elif heuristic_score >= 1:
            score += 10

        if account_age_days < 1:
            score += 10
        elif account_age_days < 60:
            score += 5

        if join_age_days < 1:
            score += 10
        elif join_age_days < 7:
            score += 5

        unique_indicators = set(indicators)
        count = len(unique_indicators)
        if count >= 6:
            score += 25
        elif count >= 4:
            score += 20
        elif count >= 3:
            score += 15
        elif count >= 2:
            score += 10
        elif count >= 1:
            score += 5

        if has_image:
            score += 10
            if has_ocr_text:
                score += 10

        if vision_indicators:
            score += 15

        if has_image and heuristic_score >= 5:
            score += 10

        if "crypto_terminology" in indicators and "giveaway_terminology" in indicators:
            score += 10

        fp_indicators = {"everyone_mention", "discord_invite", "new_account", "fresh_join"}
        only_fp = unique_indicators.issubset(fp_indicators)
        if only_fp and not has_image and heuristic_score < 5:
            return min(score, 15)

        if indicators == ["everyone_mention"]:
            return 5
        if indicators == ["discord_invite"]:
            return 5
        if not has_image and "keyword_match" not in indicators and "crypto_terminology" not in indicators and "giveaway_terminology" not in indicators:
            if heuristic_score < 5:
                return min(score, 20)

        return min(score, 100)

    def _assess_false_positive_risk(self, indicators: list, confidence: int, account_age_days: int, has_image: bool) -> str:
        signals = 0

        if account_age_days >= 60:
            signals += 1

        if has_image:
            signals += 1

        unique_cats = set(indicators)
        if len(unique_cats) >= 4:
            signals += 1

        if "crypto_terminology" in unique_cats and "keyword_match" in unique_cats:
            signals += 1

        if "everyone_mention" in unique_cats and ("keyword_match" in unique_cats or has_image):
            signals += 1

        only_safe_indicators = unique_cats.issubset({"everyone_mention", "discord_invite", "new_account", "fresh_join", "young_account", "recent_join"})
        if only_safe_indicators and not has_image:
            return "high"

        if signals >= 2:
            return "very_low"
        elif signals >= 1:
            return "low"
        elif confidence >= 60:
            return "medium"
        return "high"

    def _classify_threat(self, indicators: list, content: str) -> str:
        text_lower = content.lower()
        if "crypto" in text_lower or "usdt" in text_lower or "bitcoin" in text_lower or "ethereum" in text_lower or "wallet" in text_lower or "withdrawal" in text_lower:
            if "giveaway" in text_lower or "free" in text_lower or "claim" in text_lower:
                return "crypto_giveaway_scam"
            return "crypto_phishing"
        if "giveaway" in text_lower or "mrbeast" in text_lower or "elon" in text_lower:
            return "fake_giveaway"
        if "discord" in text_lower and ("nitro" in text_lower or "free" in text_lower):
            return "discord_phishing"
        if "judi" in text_lower or "slot" in text_lower or "gacor" in text_lower or "maxwin" in text_lower:
            return "gambling_spam"
        return "generic_scam"

    def _get_recommendation(
        self,
        classification: str,
        confidence: int,
        falsePositiveRisk: str,
        is_known_threat: bool,
        indicators: list,
        has_image: bool,
    ) -> str:
        if is_known_threat:
            return "AUTO_BAN"

        if classification == "confirmed_scam" and confidence >= 95 and len(indicators) >= 3 and falsePositiveRisk in ("very_low", "low"):
            return "AUTO_BAN"

        if classification == "confirmed_scam" and confidence >= 90 and has_image and falsePositiveRisk in ("very_low", "low"):
            return "AUTO_KICK"

        if has_image and confidence >= 85 and len(indicators) >= 3:
            return "AUTO_DELETE"

        if classification == "confirmed_scam" and confidence >= 81:
            return "AUTO_DELETE"

        if confidence >= 61:
            return "TEMP_TIMEOUT"

        if confidence >= 41:
            return "WARN"

        if confidence >= 21 and len(indicators) >= 1:
            return "MANUAL_REVIEW"

        if confidence >= 1:
            return "LOG_ONLY"

        return "IGNORE"

    def _generate_explanation(self, result: dict, content: str) -> str:
        parts = []
        if result["signatureExists"]:
            parts.append("Known scam campaign detected")
        if "everyone_mention" in result["detectedIndicators"]:
            parts.append("@everyone/@here mention")
        if "crypto_terminology" in result["detectedIndicators"]:
            parts.append("Crypto/withdrawal terminology")
        if "giveaway_terminology" in result["detectedIndicators"]:
            parts.append("Giveaway/prize terminology")
        if "new_account" in result["detectedIndicators"]:
            parts.append("New account")
        if "fresh_join" in result["detectedIndicators"]:
            parts.append("Recent join")
        if result.get("reasoning"):
            parts.extend(result["reasoning"][:3])
        return "; ".join(parts) if parts else "Multiple scam indicators detected"

    async def store_threat_signature(self, signature: dict) -> bool:
        if db is None:
            return False

        try:
            sig_id = signature.get("id") or hashlib.sha256(
                json.dumps(signature, sort_keys=True).encode()
            ).hexdigest()[:16]
            signature["id"] = sig_id
            signature["createdAt"] = signature.get("createdAt", datetime.now(timezone.utc).isoformat())
            signature["updatedAt"] = datetime.now(timezone.utc).isoformat()

            doc_ref = db.collection(THREAT_COLLECTION).document(sig_id)
            await asyncio.to_thread(doc_ref.set, signature, merge=True)

            cache_key = str(signature.get("imageHash", sig_id))
            self._threat_cache[cache_key] = signature

            print(f"[SPAM INTEL] Stored threat signature {sig_id}")
            return True
        except Exception as e:
            print(f"[SPAM INTEL] Failed to store threat signature: {e}")
            return False

    # ── Text fingerprinting & ban evasion detection ──
    BAN_PATTERNS_COLLECTION = "ban_patterns"

    async def ensure_ban_patterns_loaded(self):
        if self._ban_patterns_loaded:
            return
        await self._load_ban_patterns()
        self._ban_patterns_loaded = True

    async def _load_ban_patterns(self):
        if db is None:
            return
        try:
            docs = await asyncio.to_thread(
                lambda: list(db.collection(self.BAN_PATTERNS_COLLECTION).stream())
            )
            count = 0
            for doc in docs:
                data = doc.to_dict()
                if data and data.get("fingerprint"):
                    self._ban_patterns_cache[data["fingerprint"]] = data
                    count += 1
            print(f"[SPAM INTEL] Loaded {count} ban patterns from Firestore")
        except Exception as e:
            print(f"[SPAM INTEL] Failed to load ban patterns: {e}")

    @staticmethod
    def _compute_text_fingerprint(text: str) -> str:
        if not text:
            return ""
        text_lower = text.lower()
        parts = []

        urls = re.findall(r"https?://[^\s/\"'<>]+", text_lower, re.IGNORECASE)
        if urls:
            for u in urls:
                domain = re.sub(r"https?://(www\.)?", "", u).split("/")[0]
                parts.append(f"url:{domain}")

        scam_keywords = [
            "free nitro", "free discord", "free steam", "nitro gift", "discord gift",
            "giveaway", "you won", "you are winner", "claim now", "claim reward",
            "mrbeast", "elon musk", "free crypto", "free bitcoin", "free ethereum",
            "usdt", "bitcoin", "ethereum", "withdrawal", "withdraw",
            "invest", "profit", "bonus code", "guaranteed profit",
            "deposit", "wallet", "crypto gift",
            "slot", "judi", "gacor", "maxwin",
            "verify account", "account verification", "login verify",
            "steamcommunity", "steam communitiy",
        ]
        found_kw = [kw for kw in scam_keywords if kw in text_lower]
        if found_kw:
            parts.extend(f"kw:{kw.replace(' ', '_')}" for kw in sorted(found_kw))

        if "@everyone" in text_lower or "@here" in text_lower:
            parts.append("mention:@everyone")

        if not parts:
            return ""

        return hashlib.sha256("|".join(sorted(set(parts))).encode()).hexdigest()[:24]

    async def check_ban_pattern(
        self,
        content: str,
        account_age_days: int = 999,
    ) -> Optional[dict]:
        if account_age_days >= 60:
            return None

        fingerprint = self._compute_text_fingerprint(content)
        if not fingerprint:
            return None

        exact = self._ban_patterns_cache.get(fingerprint)
        if exact is not None:
            return {
                "matched": True,
                "matchType": "exact",
                "bannedUser": exact.get("bannedUser", "unknown"),
                "bannedAt": exact.get("bannedAt", ""),
                "originalReason": exact.get("reason", ""),
            }

        for cached_fp, data in self._ban_patterns_cache.items():
            cached_urls = set()
            for p in cached_fp.split("|"):
                if p.startswith("url:"):
                    cached_urls.add(p)
            current_urls = set()
            for p in fingerprint.split("|"):
                if p.startswith("url:"):
                    current_urls.add(p)
            if cached_urls and current_urls and cached_urls == current_urls:
                return {
                    "matched": True,
                    "matchType": "partial",
                    "bannedUser": data.get("bannedUser", "unknown"),
                    "bannedAt": data.get("bannedAt", ""),
                    "originalReason": data.get("reason", ""),
                }

        return None

    async def store_ban_pattern(
        self,
        content: str,
        reason: str,
        guild_id: str = "",
        user_id: str = "",
        user_name: str = "",
    ):
        fingerprint = self._compute_text_fingerprint(content)
        if not fingerprint:
            return

        doc_id = hashlib.sha256(f"{fingerprint}_{guild_id}".encode()).hexdigest()[:16]
        doc_ref = db.collection(self.BAN_PATTERNS_COLLECTION).document(doc_id)
        doc = await asyncio.to_thread(doc_ref.get)
        if doc.exists:
            await asyncio.to_thread(doc_ref.update, {
                "timesBanned": (doc.to_dict().get("timesBanned", 0) or 0) + 1,
                "lastBannedAt": datetime.now(timezone.utc).isoformat(),
                "lastBannedUser": user_id,
                "lastBannedGuild": guild_id,
            })
        else:
            data = {
                "fingerprint": fingerprint,
                "bannedUser": user_id,
                "bannedUserName": user_name,
                "bannedAt": datetime.now(timezone.utc).isoformat(),
                "reason": reason,
                "guildId": guild_id,
                "timesBanned": 1,
                "status": "active",
            }
            await asyncio.to_thread(doc_ref.set, data)
            self._ban_patterns_cache[fingerprint] = data

    async def build_signature(
        self,
        img_hash: int,
        confidence: int,
        category: str,
        indicators: list,
        ocr_text: str = "",
        guild_id: str = "",
        user_id: str = "",
        channel_id: str = "",
        domains: Optional[list] = None,
        wallet_addresses: Optional[list] = None,
        logos: Optional[list] = None,
        risk_indicators: Optional[list] = None,
        vision_indicators: Optional[list] = None,
    ) -> dict:
        keywords = [i for i in indicators if i not in ("everyone_mention", "new_account", "fresh_join")]
        return {
            "id": "",
            "imageHash": img_hash,
            "confidence": confidence,
            "category": category,
            "ocrFingerprint": hashlib.md5(ocr_text.encode()).hexdigest()[:16] if ocr_text else "",
            "visualEmbedding": hashlib.sha256(f"{img_hash}{ocr_text}".encode()).hexdigest()[:32] if ocr_text else "",
            "keywords": keywords,
            "logos": logos or [],
            "domains": domains or [],
            "walletAddresses": wallet_addresses or [],
            "riskIndicators": risk_indicators or indicators,
            "detectedIndicators": indicators,
            "visionIndicators": vision_indicators or [],
            "firstSeenGuild": guild_id,
            "firstSeenUser": user_id,
            "firstSeenChannel": channel_id,
            "timesDetected": 1,
            "timesConfirmed": 0,
            "falsePositiveCount": 0,
            "lastSeen": time.time(),
            "lastSeenGuild": guild_id,
            "lastSeenChannel": channel_id,
            "lastSeenUser": user_id,
            "status": "active",
        }
