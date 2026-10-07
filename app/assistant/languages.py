"""Language lists per Sarvam service (docs read 2026-10-07).

* speech to text (saaras:v4): 22 Indian languages + English, codes from the language_code enum of /speech-to-text.
* text to speech (bulbul:v3) and language identification (/text-lid): the 11 codes listed on those pages.
* chat (sarvam-105b): documented as "10 most-spoken Indian languages + English"; we expose the same 11 codes as
  text to speech and language identification (assumption: the docs give no separate code list for chat).
"""
from __future__ import annotations

NAMES = {
    "en-IN": ("English", "English"), "hi-IN": ("Hindi", "हिन्दी"), "bn-IN": ("Bengali", "বাংলা"), "gu-IN": ("Gujarati", "ગુજરાતી"),
    "kn-IN": ("Kannada", "ಕನ್ನಡ"), "ml-IN": ("Malayalam", "മലയാളം"), "mr-IN": ("Marathi", "मराठी"), "od-IN": ("Odia", "ଓଡ଼ିଆ"),
    "pa-IN": ("Punjabi", "ਪੰਜਾਬੀ"), "ta-IN": ("Tamil", "தமிழ்"), "te-IN": ("Telugu", "తెలుగు"), "as-IN": ("Assamese", "অসমীয়া"),
    "ur-IN": ("Urdu", "اردو"), "ne-IN": ("Nepali", "नेपाली"), "kok-IN": ("Konkani", "कोंकणी"), "ks-IN": ("Kashmiri", "कॉशुर"),
    "sd-IN": ("Sindhi", "सिन्धी"), "sa-IN": ("Sanskrit", "संस्कृतम्"), "sat-IN": ("Santali", "ᱥᱟᱱᱛᱟᱲᱤ"), "mni-IN": ("Manipuri", "মৈতৈলোন্"),
    "brx-IN": ("Bodo", "बड़ो"), "mai-IN": ("Maithili", "मैथिली"), "doi-IN": ("Dogri", "डोगरी"),
}
CORE = ("en-IN", "hi-IN", "bn-IN", "gu-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN", "pa-IN", "ta-IN", "te-IN")
CHAT = CORE
TTS = CORE
LID = CORE
STT = CORE + ("as-IN", "ur-IN", "ne-IN", "kok-IN", "ks-IN", "sd-IN", "sa-IN", "sat-IN", "mni-IN", "brx-IN", "mai-IN", "doi-IN")
DEFAULT = "en-IN"


def name(code: str) -> str:
    return NAMES.get(code, (code, code))[0]


def listing(codes) -> list:
    return [{"code": c, "name": NAMES[c][0], "native": NAMES[c][1]} for c in codes]


def normalise(code) -> str | None:
    """Accept 'hi', 'hi-in', 'hi-IN'; return the canonical code or None."""
    if not code or not isinstance(code, str):
        return None
    c = code.strip()
    if "-" not in c:
        c = f"{c}-IN"
    lang, _, region = c.partition("-")
    c = f"{lang.lower()}-{region.upper()}"
    return c if c in NAMES else None
