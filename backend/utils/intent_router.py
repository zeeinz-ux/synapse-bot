import re
from enum import Enum


class IntentType(Enum):
    CHAT = "chat"
    SEARCH = "search"
    ACADEMIC = "academic"
    CODING = "coding"
    RESEARCH = "research"
    SCIENCE = "science"
    HISTORY = "history"
    SPORTS = "sports"
    POLITICS = "politics"
    ECONOMY = "economy"
    TECHNOLOGY = "technology"
    HEALTH = "health"


_ACADEMIC = [
    "jurnal", "skripsi", "referensi", "doi", "penelitian",
    "journal", "thesis", "paper", "research", "citation",
    "tugas akhir", "disertasi", "ijazah",
]

_CODING = [
    "error", "bug", "debug", "python", "javascript",
    "code", "coding", "programming", "program", "function",
    "syntax", "algorithm", "variable", "api", "framework",
    "kode", "program", "fungsi", "debugging",
]

_SEARCH = [
    "carikan", "cari", "search", "temukan", "find",
    "look up", "tell me about", "what is", "who is",
    "cari info", "apa itu", "siapa itu",
]

_RESEARCH = [
    "bandingkan", "analisis", "review", "analisa",
    "compare", "analyze", "analysis", "review",
    "perbandingan", "perbedaan",
]

_SCIENCE = [
    "fisika", "kimia", "biologi", "sains", "science",
    "physics", "chemistry", "biology",
    "rumus", "formula", "eksperimen", "experiment",
    "teori", "theory", "hukum", "law of",
    "atom", "molekul", "molecule", "sel", "cell",
]

_HISTORY = [
    "sejarah", "history", "historical",
    "perang", "war", "kerajaan", "kingdom",
    "era", "zaman", "abad", "century", "decade",
    "pahlawan", "hero", "tokoh", "figure",
]

_SPORTS = [
    "olahraga", "sports", "sport", "pertandingan", "match",
    "skor", "score", "liga", "league", "turnamen", "tournament",
    "pemain", "player", "tim", "team", "klub", "club",
    "sepak bola", "football", "soccer", "basket", "tenis",
    "piala", "cup", "championship", "juara", "champion",
]

_POLITICS = [
    "politik", "politics", "political",
    "pemilu", "election", "pilkada",
    "pemerintah", "government", "kebijakan", "policy",
    "presiden", "president", "menteri", "minister",
    "undang-undang", "law", "konstitusi", "constitution",
]

_ECONOMY = [
    "ekonomi", "economy", "economic",
    "keuangan", "finance", "financial",
    "pasar", "market", "saham", "stock",
    "inflasi", "inflation", "investasi", "investment",
    "bisnis", "business", "perusahaan", "company",
    "gaji", "salary", "upah", "wage", "pajak", "tax",
]

_TECHNOLOGY = [
    "teknologi", "technology", "tech",
    "ai", "artificial intelligence", "machine learning",
    "blockchain", "cryptocurrency", "kripto",
    "cyber", "keamanan", "security", "hacker",
    "robot", "iot", "internet",
    "aplikasi", "app", "software", "hardware",
    "digital", "cloud", "data",
]

_HEALTH = [
    "kesehatan", "health", "medical", "medis",
    "penyakit", "disease", "virus", "bakteri", "bacteria",
    "obat", "medicine", "vaksin", "vaccine",
    "diet", "nutrition", "nutrisi", "olahraga",
    "rumah sakit", "hospital", "dokter", "doctor",
    "berat badan", "weight", "kalori", "calorie",
    "gejala", "symptom", "demam", "batuk",
]

_INTENT_MAP = [
    (IntentType.ACADEMIC, _ACADEMIC),
    (IntentType.CODING, _CODING),
    (IntentType.SCIENCE, _SCIENCE),
    (IntentType.HISTORY, _HISTORY),
    (IntentType.SPORTS, _SPORTS),
    (IntentType.POLITICS, _POLITICS),
    (IntentType.ECONOMY, _ECONOMY),
    (IntentType.TECHNOLOGY, _TECHNOLOGY),
    (IntentType.HEALTH, _HEALTH),
    (IntentType.RESEARCH, _RESEARCH),
    (IntentType.SEARCH, _SEARCH),
]


def _in_text(text: str, keyword: str) -> bool:
    if len(keyword) <= 4:
        return bool(re.search(rf"\b{re.escape(keyword)}\b", text))
    return keyword in text


def detect_intent(message: str) -> IntentType:
    text = message.lower()

    for intent_type, keywords in _INTENT_MAP:
        if any(_in_text(text, kw) for kw in keywords):
            return intent_type

    return IntentType.CHAT