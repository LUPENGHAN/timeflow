"""OpenAI-compatible speech-to-text client."""

import base64
from dataclasses import dataclass
from typing import Any

import httpx


class AsrError(RuntimeError):
    """Raised when speech transcription cannot be completed."""


@dataclass(slots=True)
class AsrClient:
    """Send an audio file to an OpenAI-compatible transcription endpoint."""

    api_key: str
    base_url: str
    model: str
    protocol: str = "openai_transcription"
    language: str = "zh"
    timeout_seconds: float = 60.0

    def transcribe(self, filename: str, content_type: str, audio: bytes) -> str:
        """将音频转写为文本。"""

        try:
            if self.protocol == "qwen_chat":
                return self._transcribe_qwen_chat(content_type, audio)
            if self.protocol != "openai_transcription":
                raise AsrError(f"Unsupported ASR protocol {self.protocol}.")
            return self._transcribe_openai(filename, content_type, audio)
        except AsrError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise AsrError(f"ASR request failed: {error}") from error

    def _transcribe_openai(self, filename: str, content_type: str, audio: bytes) -> str:
        """使用 OpenAI 接口转写音频。"""
        response = httpx.post(
            f"{self.base_url.rstrip('/')}/audio/transcriptions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            data={"model": self.model, "language": self.language},
            files={"file": (filename, audio, content_type)},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload: Any = response.json()
        transcript = payload.get("text") if isinstance(payload, dict) else None
        return self._validate_transcript(transcript)

    def _transcribe_qwen_chat(self, content_type: str, audio: bytes) -> str:
        """使用 Qwen Chat 接口转写音频。"""
        encoded_audio = base64.b64encode(audio).decode("ascii")
        data_uri = f"data:{content_type};base64,{encoded_audio}"
        response = httpx.post(
            f"{self.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {"data": data_uri},
                            }
                        ],
                    }
                ],
                "stream": False,
                "asr_options": {
                    "language": self.language,
                    "enable_itn": True,
                },
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        transcript = payload["choices"][0]["message"]["content"]
        return self._validate_transcript(transcript)

    def _validate_transcript(self, transcript: Any) -> str:
        """校验转写结果。"""
        if not isinstance(transcript, str) or not transcript.strip():
            raise AsrError("ASR response did not contain transcript text.")
        return transcript.strip()
