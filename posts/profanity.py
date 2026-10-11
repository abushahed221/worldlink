"""
فلتر كلمات مسيئة أساسي.
- يمكن توسيعه.
- يقبل البريد والنصوص العربية والإنجليزية.
- يُستبدل النص المسيء بـ ***
"""

import re

BAD_WORDS_AR = [
    "كلب", "حمار", "خنزير", "غبي", "أحمق", "حثالة", "قذر",
    "لعنة", "زبالة", "حقير", "تافه", "يا حيوان",
    "قذر", "خسيس", "نذل", "سافل", "وقح",
]

BAD_WORDS_EN = [
    "fuck", "shit", "bitch", "asshole", "bastard", "damn",
    "cunt", "dick", "pussy", "whore", "slut", "nigger", "faggot",
    "retard", "moron", "idiot",
]

# أنماط لتجاوز الكتابة
LEET_MAP = {
    "@": "a", "0": "o", "1": "i", "3": "e",
    "$": "s", "5": "s", "7": "t", "+": "t",
    "!": "i",
}


def _normalize(text):
    text = text.lower()
    for k, v in LEET_MAP.items():
        text = text.replace(k, v)
    text = re.sub(r"[\.\-_\*]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def contains_profanity(text):
    """يُرجع True لو النص فيه كلمة مسيئة."""
    if not text:
        return False
    normalized = _normalize(text)
    for word in BAD_WORDS_EN:
        if word in normalized:
            return True
    for word in BAD_WORDS_AR:
        if word in text:
            return True
    return False


def censor(text):
    """يستبدل الكلمات المسيئة بـ ***."""
    if not text:
        return text
    result = text
    for word in BAD_WORDS_AR + BAD_WORDS_EN:
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        result = pattern.sub("*" * len(word), result)
    return result


def check_and_report(text, ip="", username=""):
    """
    يفحص النص. لو مسيء:
    - يسجّل في logger
    - يُرجع (True, cleaned_text)
    """
    import logging
    logger = logging.getLogger("worldlink.security")
    if contains_profanity(text):
        logger.warning(f"PROFANITY: ip={ip} user={username} preview={text[:80]}")
        return True, censor(text)
    return False, text