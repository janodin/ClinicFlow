import re

from .models import VoiceAgentSettings


BASE_SPEECH_HINTS = {
    VoiceAgentSettings.EMOTION_NEUTRAL: {"rate": 1.0, "pitch": 1.0},
    VoiceAgentSettings.EMOTION_WARM: {"rate": 0.98, "pitch": 1.04},
    VoiceAgentSettings.EMOTION_REASSURING: {"rate": 0.92, "pitch": 0.98},
    VoiceAgentSettings.EMOTION_CONCISE: {"rate": 1.06, "pitch": 1.0},
    VoiceAgentSettings.EMOTION_CELEBRATORY: {"rate": 1.02, "pitch": 1.08},
}

INTENSITY_SCALE = {
    VoiceAgentSettings.EMOTION_INTENSITY_SUBTLE: 0.5,
    VoiceAgentSettings.EMOTION_INTENSITY_BALANCED: 1.0,
    VoiceAgentSettings.EMOTION_INTENSITY_EXPRESSIVE: 1.25,
}

MIN_RATE = 0.85
MAX_RATE = 1.12
MIN_PITCH = 0.92
MAX_PITCH = 1.12


def _choice_values(choices):
    return {choice[0] for choice in choices}


def _safe_emotion(value):
    normalized = str(value or "").strip()
    if normalized in _choice_values(VoiceAgentSettings.EMOTION_CHOICES):
        return normalized
    return VoiceAgentSettings.EMOTION_NEUTRAL


def _safe_intensity(value):
    normalized = str(value or "").strip()
    if normalized in _choice_values(VoiceAgentSettings.EMOTION_INTENSITY_CHOICES):
        return normalized
    return VoiceAgentSettings.EMOTION_INTENSITY_BALANCED


def _clamp(value, minimum, maximum):
    return min(max(value, minimum), maximum)


def _scaled_hint(base_value, scale):
    return 1.0 + ((base_value - 1.0) * scale)


def voice_emotion_profile(emotion, intensity):
    safe_emotion = _safe_emotion(emotion)
    safe_intensity = _safe_intensity(intensity)
    base = BASE_SPEECH_HINTS[safe_emotion]
    scale = INTENSITY_SCALE[safe_intensity]
    return {
        "emotion": safe_emotion,
        "emotion_intensity": safe_intensity,
        "speech": {
            "rate": round(_clamp(_scaled_hint(base["rate"], scale), MIN_RATE, MAX_RATE), 2),
            "pitch": round(_clamp(_scaled_hint(base["pitch"], scale), MIN_PITCH, MAX_PITCH), 2),
        },
    }


def resolve_voice_emotion(message, reply_text, voice_settings):
    if not voice_settings or voice_settings.safe_emotion_mode == VoiceAgentSettings.EMOTION_MODE_OFF:
        return VoiceAgentSettings.EMOTION_NEUTRAL
    text = f"{message or ''}\n{reply_text or ''}".lower()
    if voice_settings.safe_emotion_mode == VoiceAgentSettings.EMOTION_MODE_FIXED:
        if _neutral_required(text):
            return VoiceAgentSettings.EMOTION_NEUTRAL
        if _reassuring_needed(text):
            return VoiceAgentSettings.EMOTION_REASSURING
        return voice_settings.safe_fixed_emotion

    if _neutral_required(text):
        return VoiceAgentSettings.EMOTION_NEUTRAL
    if _reassuring_needed(text):
        return VoiceAgentSettings.EMOTION_REASSURING
    if _celebratory_allowed(text):
        return VoiceAgentSettings.EMOTION_CELEBRATORY
    if _concise_preferred(text):
        return VoiceAgentSettings.EMOTION_CONCISE
    return VoiceAgentSettings.EMOTION_WARM


def voice_style_guidance(emotion, intensity):
    safe_emotion = _safe_emotion(emotion)
    safe_intensity = _safe_intensity(intensity)
    return "\n".join([
        "Voice delivery style:",
        f"- Current emotion: {safe_emotion}.",
        f"- Emotion intensity: {safe_intensity}.",
        "- Keep the reply short enough to speak aloud clearly.",
        "- Emotion affects wording only. It must not override clinic data, tool results, appointment confirmation, availability, safety, privacy, or tenant rules.",
    ])


def _neutral_required(text):
    value = str(text or "").lower()
    return bool(re.search(r"\b(cancel|cancelled|canceled|privacy|policy|not medical advice|emergency|urgent|out of scope|cannot help with that|system integrations|technical implementation)\b", value))


def _celebratory_allowed(text):
    value = str(text or "").lower()
    return bool(re.search(r"\b(your\b[^.\n]*\bis booked for|has been booked for|has been successfully booked for|successfully booked\b[^.\n]*\bfor|has been rescheduled for)\b", value))


def _reassuring_needed(text):
    value = str(text or "").lower()
    if re.search(r"\b(?:not|was not|wasn't|isn't|hasn't|failed|unable|could not|couldn't|didn't|can't|cannot)\b(?:\W+\w+){0,4}\W+book(?:ed)?\b", value):
        return True
    return bool(re.search(r"\b(confused|unsure|not sure|worried|anxious|nervous|blocked|trouble|unavailable|not available|no slots|fully booked|already booked|time is booked|slot is booked|booked by another|not successfully booked|not booked|failed to book|could not be booked|could not|can't hear|cannot hear)\b", value))


def _concise_preferred(text):
    value = str(text or "").lower()
    return bool(re.search(r"\b(hours?|open|closed|location|address|where|services?|phone|email|contact)\b", value))
