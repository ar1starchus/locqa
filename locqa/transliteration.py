from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


class KazakhLatinTransliteration:
    """Official Kazakh Cyrillic to Latin transliteration engine
    (based on the approved state standard Latin alphabet) with length verification.
    
    Preserves:
    - Flutter placeholders {name}, {count}
    - HTML/markup tags <g>...</g>
    - Escape sequences \\n, \\t
    """

    CHAR_MAP: Dict[str, str] = {
        # Lowercase
        "а": "a", "ә": "ä", "б": "b", "в": "v", "г": "g", "ғ": "ğ", "д": "d",
        "е": "e", "ё": "yo", "ж": "j", "з": "z", "и": "i", "й": "i", "і": "i",
        "к": "k", "қ": "q", "л": "l", "м": "m", "н": "n", "ң": "ñ", "о": "o",
        "ө": "ö", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ұ": "u",
        "ү": "ü", "ф": "f", "х": "h", "һ": "h", "ц": "c", "ч": "ç", "ш": "ş",
        "щ": "ş", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
        # Uppercase
        "А": "A", "Ә": "Ä", "Б": "B", "В": "V", "Г": "G", "Ғ": "Ğ", "Д": "D",
        "Е": "E", "Ё": "Yo", "Ж": "J", "З": "Z", "И": "I", "Й": "I", "І": "I",
        "К": "K", "Қ": "Q", "Л": "L", "М": "M", "Н": "N", "Ң": "Ñ", "О": "O",
        "Ө": "Ö", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U", "Ұ": "U",
        "Ү": "Ü", "Ф": "F", "Х": "H", "Һ": "H", "Ц": "C", "Ч": "Ç", "Ш": "Ş",
        "Щ": "Ş", "Ъ": "", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "Yu", "Я": "Ya",
    }

    @classmethod
    def transliterate_text(cls, text: str) -> str:
        """Transliterate Cyrillic Kazakh text to official Latin script
        while shielding placeholders and tags.
        """
        if not text:
            return ""

        # Protect placeholders and markup tokens
        protected_tokens: List[str] = []

        def token_repl(match):
            idx = len(protected_tokens)
            protected_tokens.append(match.group(0))
            return f"__TOKEN_{idx}__"

        shielded = re.sub(r"\{[a-zA-Z0-9_]+\}|<[^>]+>|%[a-zA-Z0-9_\$]+", token_repl, text)

        # Transliterate character by character
        result_chars = [cls.CHAR_MAP.get(ch, ch) for ch in shielded]
        transliterated = "".join(result_chars)

        # Restore protected tokens
        for idx, token in enumerate(protected_tokens):
            transliterated = transliterated.replace(f"__TOKEN_{idx}__", token)

        return transliterated

    @classmethod
    def verify_lengths(
        cls,
        cyrillic_entries: Dict[str, str],
        max_growth_percent: float = 30.0,
    ) -> List[Tuple[str, str, str, int, int, float]]:
        """Verify length delta of Latin transliteration against original Cyrillic strings.
        
        Returns list of (key, cyrillic, latin, len_cyrillic, len_latin, growth_percent)
        for strings that grow significantly.
        """
        overflows = []
        for key, text in cyrillic_entries.items():
            if not text:
                continue
            latin = cls.transliterate_text(text)
            len_c = len(text)
            len_l = len(latin)
            if len_c > 0 and len_l > len_c:
                growth = ((len_l - len_c) / len_c) * 100.0
                if growth > max_growth_percent and (len_l - len_c) >= 5:
                    overflows.append((key, text, latin, len_c, len_l, growth))

        return overflows
