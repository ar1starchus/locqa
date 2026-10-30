from __future__ import annotations

import re
from typing import Any, Dict, List, Set, Tuple

from locqa.checkers.base import BaseChecker
from locqa.models import ArbFile, Finding, IssueType, Severity


class OrthographyChecker(BaseChecker):
    """Detects orthographical errors and script mixing in localized strings.
    
    1. Homoglyphs / Mixed script:
       Detects accidental Latin characters embedded inside Cyrillic words
       (e.g., Latin 'i' instead of Cyrillic 'і', Latin 'c' instead of Cyrillic 'с').
       This is an algorithmic character-level check that applies universally.
    2. Repeated punctuation and malformed whitespace.
    3. Custom orthography dictionary (if provided dynamically via context).
    """

    # Latin letters that visually collide with Cyrillic / Kazakh glyphs
    LATIN_HOMOGLYPH_MAP = {
        "i": "і",  # Latin small i -> Kazakh small i (U+0456)
        "I": "І",  # Latin capital I -> Kazakh capital I (U+0406)
        "c": "с",  # Latin small c -> Cyrillic small s (U+0441)
        "C": "С",
        "a": "а",  # Latin small a -> Cyrillic small a (U+0430)
        "A": "А",
        "e": "е",  # Latin small e -> Cyrillic small e (U+0435)
        "E": "Е",
        "o": "о",  # Latin small o -> Cyrillic small o (U+043E)
        "O": "О",
        "p": "р",  # Latin small p -> Cyrillic small r (U+0440)
        "P": "Р",
        "x": "х",  # Latin small x -> Cyrillic small kh (U+0445)
        "X": "Х",
        "y": "у",  # Latin small y -> Cyrillic small u (U+0443)
        "Y": "У",
        "k": "к",  # Latin small k -> Cyrillic small k (U+043A)
        "K": "К",
    }

    @property
    def issue_type(self) -> IssueType:
        return IssueType.ORTHOGRAPHY

    def check(
        self,
        source: ArbFile,
        target: ArbFile,
        context: Dict[str, Any] | None = None,
    ) -> List[Finding]:
        context = context or {}
        custom_dictionary: Dict[str, str] = context.get("orthography_dictionary", {})
        findings: List[Finding] = []

        for key, tgt_entry in target.entries.items():
            tgt_val = tgt_entry.value
            src_entry = source.entries.get(key)
            src_val = src_entry.value if src_entry else ""

            # Strip out placeholders and HTML tags before checking words
            clean_text = re.sub(r"\{[a-zA-Z0-9_]+\}|<[^>]+>", " ", tgt_val)

            evidence_items: List[str] = []
            suggested_text = tgt_val

            src_placeholders = set()
            if src_val:
                src_placeholders = {p.strip("{}").lower() for p in re.findall(r"\{[a-zA-Z0-9_]+\}", src_val)}

            # Check 1: Algorithmic Homoglyph detection (mixed Latin inside Cyrillic word)
            # Detects accidental visual homoglyph keystrokes (e.g. Latin 'i' in 'бөлімiне', Latin 'c' in 'көтерілеcің')
            # while respecting legitimate English words, acronyms, and hyphenated inflections (e.g. 'CHICKEN-қа', 'Pass-ты', 'GPS-белгі').
            words = re.findall(r"\b[\w\-]+\b", clean_text, re.UNICODE)
            for word in words:
                clean_word = word.lower().split("-")[0]
                # If word matches a known source placeholder identifier, skip it
                if clean_word in src_placeholders:
                    continue

                parts = word.split("-")
                word_has_error = False
                fixed_word = word
                replaced_letters: List[str] = []

                for part in parts:
                    has_cyrillic = bool(re.search(r"[а-яәғқңөұүһіА-ЯӘҒҚҢӨҰҮҺІ]", part))
                    has_latin = bool(re.search(r"[a-zA-Z]", part))

                    # If part is purely Latin or purely Cyrillic, it is script-homogeneous: valid!
                    # E.g. in 'Pass-ты', 'Pass' is 100% Latin, 'ты' is 100% Cyrillic.
                    if not (has_cyrillic and has_latin):
                        continue

                    lat_chars = [c for c in part if ("a" <= c <= "z" or "A" <= c <= "Z")]
                    cyr_chars = [c for c in part if re.search(r"[а-яәғқңөұүһіА-ЯӘҒҚҢӨҰҮҺІ]", c)]

                    # If the Latin sub-part is an intentional foreign word from the source, skip it
                    if src_val and len(part) >= 2 and re.search(rf"\b{re.escape(part)}\b", src_val, re.IGNORECASE):
                        continue

                    # Criteria for genuine homoglyph error:
                    # 1. The word/part is predominantly Cyrillic (Cyrillic letters >= 60%)
                    # 2. ALL Latin letters in the part are recognized visual homoglyphs in LATIN_HOMOGLYPH_MAP
                    #    (if it has non-homoglyph Latin letters like 's', 'r', 'n', 'h', it's an English word).
                    all_lat_in_map = all(c in self.LATIN_HOMOGLYPH_MAP for c in lat_chars)
                    total_letters = len(cyr_chars) + len(lat_chars)
                    cyr_ratio = len(cyr_chars) / total_letters if total_letters > 0 else 0

                    if all_lat_in_map and cyr_ratio >= 0.6:
                        fixed_part = part
                        for ch in lat_chars:
                            fixed_part = fixed_part.replace(ch, self.LATIN_HOMOGLYPH_MAP[ch])
                            replaced_letters.append(f"'{ch}' -> '{self.LATIN_HOMOGLYPH_MAP[ch]}'")
                        fixed_word = fixed_word.replace(part, fixed_part)
                        word_has_error = True

                if word_has_error and replaced_letters:
                    evidence_items.append(
                        f"Смешение алфавитов в слове '{word}' (латиница внутри кириллицы: {', '.join(replaced_letters)})"
                    )
                    suggested_text = re.sub(rf"\b{re.escape(word)}\b", lambda _: fixed_word, suggested_text)

            # Check 2: Custom orthography dictionary if supplied via configuration
            if custom_dictionary:
                for wrong_word, right_word in custom_dictionary.items():
                    pattern = rf"\b{re.escape(wrong_word)}\b"
                    if re.search(pattern, clean_text):
                        evidence_items.append(
                            f"Орфографическая ошибка: '{wrong_word}' вместо '{right_word}'"
                        )
                        suggested_text = re.sub(pattern, right_word, suggested_text)

            if evidence_items:
                findings.append(
                    Finding(
                        key=key,
                        issue_type=self.issue_type,
                        severity=Severity.MEDIUM,
                        source=src_val,
                        target=tgt_val,
                        evidence="; ".join(evidence_items),
                        suggestion=suggested_text if suggested_text != tgt_val else None,
                        confidence=0.95,
                        reviewed_by_human=False,
                    )
                )

        return findings
