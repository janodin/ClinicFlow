import re


KEYWORD_MAP = {
    "hour": ["hours", "open", "close", "time", "schedule", "when"],
    "price": ["price", "cost", "fee", "how much", "rate", "payment"],
    "location": ["location", "address", "where", "find", "map", "directions"],
    "contact": ["contact", "phone", "call", "email", "reach"],
    "service": ["service", "treatment", "procedure", "offer", "what do you do"],
    "book": ["book", "appointment", "schedule", "reserve", "slot"],
    "faq": ["faq", "question", "help", "info"],
}


def _extract_keywords(text):
    lowered = text.lower()
    tokens = re.findall(r"\b\w+\b", lowered)
    found = set()
    for category, words in KEYWORD_MAP.items():
        for word in words:
            if word in lowered or any(word in t for t in tokens):
                found.add(category)
                break
    return found


def match_faq(clinic, text):
    keywords = _extract_keywords(text)
    if not keywords:
        return None
    faqs = clinic.faqs.filter(is_active=True)
    for faq in faqs:
        faq_keywords = _extract_keywords(faq.question + " " + faq.answer)
        if keywords & faq_keywords:
            return faq
    return None
