from dataclasses import dataclass

from .models import VoiceAgentSettings


@dataclass(frozen=True)
class VoiceReply:
    text: str
    provider_payload: dict


class BrowserVoiceAdapter:
    provider = VoiceAgentSettings.PROVIDER_BROWSER

    def reply_payload(self, text):
        clean_text = str(text or "").strip()
        return VoiceReply(text=clean_text, provider_payload={"type": "browser_speech", "text": clean_text})

    def verify_webhook(self, request):
        return False


def get_voice_adapter(provider):
    if provider == VoiceAgentSettings.PROVIDER_BROWSER:
        return BrowserVoiceAdapter()
    return BrowserVoiceAdapter()
