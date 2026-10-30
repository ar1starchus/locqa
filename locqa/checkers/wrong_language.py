from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from locqa.checkers.base import BaseChecker
from locqa.models import ArbFile, Finding, IssueType, Severity


class WrongLanguageChecker(BaseChecker):
    """Detects text written in an unexpected language or script within the target localization file.
    
    Uses purely algorithmic and statistical criteria:
    1. Script-level mismatch:
       - Cyrillic target (e.g. Kazakh Cyrillic): flags multi-word Latin phrases not matching global brands.
       - Latin target (e.g. Uzbek Latin): flags Cyrillic Russian text blocks.
    2. Phonotactic / orthographic markers:
       - Uzbek Latin apostrophes: o‘, g‘, o', g'
       - Common English functional stopwords (the, and, for, with, this, that)
    3. Dynamic cross-locale collision check:
       - If auxiliary ARB files are provided (e.g. --aux uz=intl_uz.arb en=intl_en.arb),
         checks if target[key] matches the translation of another locale exactly.
    """

    # Uzbek Latin orthographic markers: vowel/consonant followed by inverted comma/apostrophe
    UZBEK_APOSTROPHE_MARKER = re.compile(r"[oOgG][\u2018\u2019'`]\w*", re.UNICODE)

    # Standard English functional stopwords
    ENGLISH_STOPWORDS = re.compile(
        r"\b(the|and|for|with|this|that|your|have|from|will|must|should|item|equipped|season|pass|reward|player|event|update)\b",
        re.IGNORECASE,
    )

    # Universal brand / acronym filter
    GLOBAL_BRANDS: Set[str] = {
        "BATTLE PASS", "GRAND", "GRAND MOBILE", "ROLE PLAY", "MOBILE",
        "DISCORD", "TELEGRAM", "GOOGLE", "APPLE", "TWITTER", "VK", "VK PAY", "LATAM",
        "SPAIN", "JACKPOT", "FPS", "HUD", "CDN", "API", "DEV", "ID", "VIP",
        "LVL", "EXP", "GC", "ROSTICS", "CHICKEN", "CARBALL LEAGUE", "SUMMER RUSH",
        "SEASON PASS", "1XBET", "SILVERSTAR",
    }

    @property
    def issue_type(self) -> IssueType:
        return IssueType.WRONG_LANGUAGE

    def is_brand_or_code(self, text: str) -> bool:
        s = text.strip()
        if not s:
            return True
        if re.fullmatch(r"[\d\s\W%_{}\\\/–—#@\$\+\*\:\;\,\.\?\!\(\)\[\]\uea34]+", s):
            return True
        upper = s.upper()
        if any(b in upper for b in self.GLOBAL_BRANDS) and len(s.split()) <= 4:
            return True
        if s.startswith("http://") or s.startswith("https://"):
            return True
        return False

    def check(
        self,
        source: ArbFile,
        target: ArbFile,
        context: Dict[str, Any] | None = None,
    ) -> List[Finding]:
        context = context or {}
        findings: List[Finding] = []
        target_locale = (target.locale or "").lower()

        aux_files: Dict[str, ArbFile] = context.get("auxiliary_arb_files", {})
        uz_arb = aux_files.get("uz")
        en_arb = aux_files.get("en")

        for key, tgt_entry in target.entries.items():
            tgt_val = tgt_entry.value.strip()
            src_entry = source.entries.get(key)
            src_val = src_entry.value.strip() if src_entry else ""

            if not tgt_val or self.is_brand_or_code(tgt_val):
                continue

            clean_text = re.sub(r"\{[a-zA-Z0-9_]+\}|<[^>]+>", " ", tgt_val).strip()
            clean_src = re.sub(r"\{[a-zA-Z0-9_]+\}|<[^>]+>", " ", src_val).strip()
            if not clean_text or len(clean_text) < 4:
                continue

            # Universal Rule for Brands & Preserved English terms:
            # If the target text is identical to source, or all its Latin words were already
            # present in the Russian source, it is an approved English brand, car model,
            # technical term, or phrase preserved from the source original.
            if clean_text.lower() == clean_src.lower():
                continue

            tgt_latin_words = set(re.findall(r"[a-zA-Z]+", clean_text.lower()))
            src_latin_words = set(re.findall(r"[a-zA-Z]+", clean_src.lower()))
            if tgt_latin_words and tgt_latin_words.issubset(src_latin_words):
                continue

            detected_lang = None
            evidence = ""

            # Check 1: Cross-locale ARB collision (dynamic, zero hardcoded words)
            if uz_arb and key in uz_arb.entries:
                uz_val = uz_arb.entries[key].value.strip()
                if uz_val and tgt_val == uz_val and target_locale != "uz":
                    # If target is identical to Uzbek translation and has Latin words
                    if re.search(r"[a-zA-Z]", tgt_val) and not self.is_brand_or_code(tgt_val):
                        detected_lang = "Uzbek (Latin)"
                        evidence = f"Текст полностью совпадает с переводом в узбекском файле локализации: '{tgt_val}'"

            if not detected_lang and en_arb and key in en_arb.entries:
                en_val = en_arb.entries[key].value.strip()
                if en_val and tgt_val == en_val and target_locale != "en":
                    if len(tgt_val.split()) >= 3 and not self.is_brand_or_code(tgt_val):
                        detected_lang = "English"
                        evidence = f"Текст полностью совпадает с английским переводом ключа '{key}': '{tgt_val}'"

            # Check 2: Script-level analysis
            if not detected_lang:
                if target_locale in ("kk", "kz"):
                    has_latin = bool(re.search(r"[a-zA-Z]", clean_text))
                    has_cyrillic = bool(re.search(r"[а-яәғқңөұүһіА-ЯӘҒҚҢӨҰҮҺІ]", clean_text))

                    if has_latin and not has_cyrillic:
                        if self.UZBEK_APOSTROPHE_MARKER.search(clean_text):
                            detected_lang = "Uzbek (Latin)"
                            evidence = f"Обнаружена узбекская латиница с характерными апострофами (o'/g'): '{tgt_val}'"
                        elif self.ENGLISH_STOPWORDS.search(clean_text) and len(clean_text.split()) >= 2:
                            detected_lang = "English"
                            evidence = f"Текст содержит служебные слова английского языка: '{tgt_val}'"
                        elif len(clean_text.split()) >= 3:
                            detected_lang = "Foreign (Latin)"
                            evidence = f"Строка полностью на латинице в казахской кириллической локализации: '{tgt_val}'"

                elif target_locale == "uz":
                    has_cyrillic = bool(re.search(r"[а-яА-ЯёЁ]", clean_text))
                    has_latin = bool(re.search(r"[a-zA-Z]", clean_text))
                    if has_cyrillic and not has_latin and len(clean_text.split()) >= 2:
                        detected_lang = "Russian (Cyrillic)"
                        evidence = f"Кириллический текст в узбекской латинской локализации: '{tgt_val}'"

            if detected_lang:
                findings.append(
                    Finding(
                        key=key,
                        issue_type=self.issue_type,
                        severity=Severity.HIGH,
                        source=src_val,
                        target=tgt_val,
                        evidence=evidence,
                        suggestion=None,
                        confidence=0.95,
                        reviewed_by_human=False,
                    )
                )

        return findings
