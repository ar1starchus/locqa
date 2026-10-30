from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional


class GeminiClient:
    """Gemini API client for semantic localization QA and translation suggestions.
    
    Uses standard REST API over HTTPS, requiring no third-party SDK dependencies.
    Gracefully handles absence of GEMINI_API_KEY.
    """

    DEFAULT_MODEL = "gemini-1.5-flash"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.model = model or os.environ.get("GEMINI_MODEL") or self.DEFAULT_MODEL

    @property
    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def analyze_translations(
        self,
        batch: List[Dict[str, str]],
        source_lang: str = "ru",
        target_lang: str = "kk",
    ) -> List[Dict[str, Any]]:
        """Evaluate a batch of (source, target) localization pairs for machine translation calques,
        unnatural word order, and suggest natural human corrections.
        """
        if not self.is_available:
            return []

        prompt = (
            f"You are a professional localization QA specialist evaluating {target_lang} game translation from {source_lang}.\n"
            f"Analyze the following items. Identify any that suffer from 'machine_translation_suspect' "
            f"(literal word-for-word calque, unnatural word order, Russian grammar projected onto Kazakh/Uzbek).\n\n"
            f"Input items:\n"
            f"{json.dumps(batch, ensure_ascii=False, indent=2)}\n\n"
            f"Output strictly a JSON list of objects for any suspicious items:\n"
            f'[{{"key": "...", "evidence": "brief explanation in Russian", "suggestion": "natural native translation", "confidence": 0.9}}]\n'
            f"If an item is natural native phrasing, do not include it."
        )

        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        )

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }

        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text_response = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text_response)
        except Exception as e:
            # Fallback or log without failing execution
            return []
