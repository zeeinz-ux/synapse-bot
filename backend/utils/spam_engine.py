import re
from datetime import datetime, timezone

class SpamEngine:
    def __init__(self):
        # Regex untuk link mencurigakan dan keyword judi
        self.banned_patterns = [
            r"https?://(bit\.ly|t\.co|tinyurl\.com|shorturl\.at)", # Shortener link
            r"(slot|judi|deposit|gacor|win)", # Keyword umum
            r"(join now|click here|free crypto|giveaway)"
        ]
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.banned_patterns]

    def get_risk_score(self, message) -> int:
        score = 0
        
        # Layer 1: Heuristic (Ringan)
        if message.mention_everyone: score += 5
        
        # Check kata kunci
        for pattern in self.compiled_patterns:
            if pattern.search(message.content):
                score += 3
        
        # Layer 2: Account Age (User Context)
        account_age = (datetime.now(timezone.utc) - message.author.created_at).days
        if account_age < 1: # Akun baru banget
            score += 4
            
        return score