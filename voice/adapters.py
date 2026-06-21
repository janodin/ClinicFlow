from dataclasses import dataclass

from .models import VoiceAgentSettings


@dataclass(frozen=True)
class VoiceReply:
    text: str
    provider_payload: dict


class BrowserVoiceAdapter:
    provider = VoiceAgentSettings.PROVIDER_BROWSER

    def reply_payload(self, text, emotion_profile=None):
        clean_text = str(text or "").strip()
        payload = {"type": "browser_speech", "text": clean_text}
        if isinstance(emotion_profile, dict):
            emotion = str(emotion_profile.get("emotion") or "").strip()
            intensity = str(emotion_profile.get("emotion_intensity") or "").strip()
            speech = emotion_profile.get("speech")
            if emotion:
                payload["emotion"] = emotion
            if intensity:
                payload["emotion_intensity"] = intensity
            if isinstance(speech, dict):
                payload["speech"] = speech
        return VoiceReply(text=clean_text, provider_payload=payload)

    def verify_webhook(self, request):
        return False


def get_voice_adapter(provider):
    if provider == VoiceAgentSettings.PROVIDER_BROWSER:
        return BrowserVoiceAdapter()
    return BrowserVoiceAdapter()
