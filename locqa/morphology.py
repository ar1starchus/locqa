from __future__ import annotations

import re
from typing import List, Optional, Set


class KazakhMorphology:
    """Offline morphological analyzer and inflection engine for Kazakh.
    
    Implements:
    1. Vowel harmony rules (Жуан / жіңішке үндестігі)
    2. Consonant assimilation rules (Қатаң / ұяң / үнді үндестігі)
    3. Affix decomposition (Plural, Possessive, Case)
    4. Suffix transfer: extracts the grammatical category from a mistranslated word
       and synthesizes the grammatically matched form on the approved glossary term.
    """

    FRONT_VOWELS: Set[str] = set("әөүіеэи")
    BACK_VOWELS: Set[str] = set("аоұыяёю")
    ALL_VOWELS: Set[str] = FRONT_VOWELS | BACK_VOWELS

    VOICELESS_CONSONANTS: Set[str] = set("пфкқтсшщхцчһ")
    SONORANT_OR_VOICED: Set[str] = set("рлйумнңбвгғджз")

    @classmethod
    def is_front_harmony(cls, word: str) -> bool:
        """Check if word follows front (soft) vowel harmony based on its last vowel."""
        for ch in reversed(word.lower()):
            if ch in cls.ALL_VOWELS:
                return ch in cls.FRONT_VOWELS
        return True

    @classmethod
    def analyze_affixes(cls, word: str, stem: str) -> List[str]:
        """Extract grammatical tags (PLURAL, POSSESSIVE, CASE) attached to stem in word."""
        stem_clean = stem.lower().rstrip("қкп")
        # Match word starting with stem root (allowing consonant alternations қ->ғ, к->г, п->б)
        m = re.match(rf"^{re.escape(stem_clean)}[қкпғгб]?(.*)$", word.lower())
        if not m:
            return []

        s = m.group(1)
        if not s:
            return []

        tags: List[str] = []

        # 1. Plural suffixes (-тар, -тер, -дар, -дер, -лар, -лер)
        m_pl = re.match(r"^(тар|тер|дар|дер|лар|лер)", s)
        if m_pl:
            tags.append("PLURAL")
            s = s[len(m_pl.group(0)) :]

        # 2. Possessive suffixes (Тәуелдік)
        m_p2f = re.match(r"^(ыңыз|іңіз|ңыз|ңіз)", s)
        m_p1p = re.match(r"^(ымыз|іміз|мыз|міз)", s)
        m_p3 = re.match(r"^(сы|сі|ы|і)", s)
        m_p1s = re.match(r"^(ым|ім|м)", s)
        m_p2i = re.match(r"^(ың|ің|ң)", s)

        if m_p2f:
            tags.append("POSS_2_FORMAL")  # ваш (вежливое)
            s = s[len(m_p2f.group(0)) :]
        elif m_p1p:
            tags.append("POSS_1_PLURAL")  # наш
            s = s[len(m_p1p.group(0)) :]
        elif m_p3:
            tags.append("POSS_3")  # его / ее / их
            s = s[len(m_p3.group(0)) :]
        elif m_p1s:
            tags.append("POSS_1_SINGULAR")  # мой
            s = s[len(m_p1s.group(0)) :]
        elif m_p2i:
            tags.append("POSS_2_INFORMAL")  # твой
            s = s[len(m_p2i.group(0)) :]

        # 3. Case suffixes (Септік)
        if re.match(r"^(ға|ге|қа|ке|на|не)", s):
            tags.append("DAT")  # Барыс (кому? чему? куда?)
        elif re.match(r"^(ды|ді|ты|ті|ны|ні|н)$", s):
            tags.append("ACC")  # Табыс (кого? что?)
        elif re.match(r"^(да|де|та|те|нда|нде)", s):
            tags.append("LOC")  # Жатыс (где?)
        elif re.match(r"^(дан|ден|тан|тен|нан|нен)", s):
            tags.append("ABL")  # Шығыс (откуда?)
        elif re.match(r"^(ның|нің|дың|дің|тың|тің)", s):
            tags.append("GEN")  # Ілік (чей?)
        elif re.match(r"^(мен|бен|пен)", s):
            tags.append("INS")  # Көмектес (с кем?)

        return tags

    @classmethod
    def inflect(cls, stem: str, tags: List[str]) -> str:
        """Apply a sequence of grammatical tags to stem obeying vowel & consonant harmony."""
        if not tags:
            return stem

        is_front = cls.is_front_harmony(stem)
        cur = stem.lower()

        for tag in tags:
            last_ch = cur[-1]
            ends_with_vowel = last_ch in cls.ALL_VOWELS
            ends_with_voiceless = last_ch in cls.VOICELESS_CONSONANTS

            if tag == "PLURAL":
                if ends_with_vowel or last_ch in "рлйу":
                    sfx = "лер" if is_front else "лар"
                elif last_ch in "мнңздж":
                    sfx = "дер" if is_front else "дар"
                else:
                    sfx = "тер" if is_front else "тар"
                cur += sfx

            elif tag == "POSS_2_FORMAL":
                if ends_with_vowel:
                    sfx = "ңіз" if is_front else "ңыз"
                else:
                    sfx = "іңіз" if is_front else "ыңыз"
                cur += sfx

            elif tag == "POSS_1_PLURAL":
                if ends_with_vowel:
                    sfx = "міз" if is_front else "мыз"
                else:
                    sfx = "іміз" if is_front else "ымыз"
                cur += sfx

            elif tag == "POSS_3":
                if ends_with_vowel:
                    sfx = "сі" if is_front else "сы"
                else:
                    sfx = "і" if is_front else "ы"
                cur += sfx

            elif tag == "POSS_1_SINGULAR":
                if ends_with_vowel:
                    sfx = "м"
                else:
                    sfx = "ім" if is_front else "ым"
                cur += sfx

            elif tag == "POSS_2_INFORMAL":
                if ends_with_vowel:
                    sfx = "ң"
                else:
                    sfx = "ің" if is_front else "ың"
                cur += sfx

            elif tag == "ACC":
                # Special rule: 3rd person possessive (-сы/-сі/-ы/-і) takes -н in accusative
                if cur.endswith(("сы", "сі", "ы", "і")):
                    sfx = "н"
                elif ends_with_vowel:
                    sfx = "ні" if is_front else "ны"
                elif ends_with_voiceless:
                    sfx = "ті" if is_front else "ты"
                else:
                    sfx = "ді" if is_front else "ды"
                cur += sfx

            elif tag == "DAT":
                # Special rule: 3rd person possessive takes -на/-не in dative
                if cur.endswith(("сы", "сі", "ы", "і")):
                    sfx = "не" if is_front else "на"
                elif ends_with_voiceless:
                    sfx = "ке" if is_front else "қа"
                else:
                    sfx = "ге" if is_front else "ға"
                cur += sfx

            elif tag == "LOC":
                if cur.endswith(("сы", "сі", "ы", "і")):
                    sfx = "нде" if is_front else "нда"
                elif ends_with_voiceless:
                    sfx = "те" if is_front else "та"
                else:
                    sfx = "де" if is_front else "да"
                cur += sfx

            elif tag == "ABL":
                if cur.endswith(("сы", "сі", "ы", "і")):
                    sfx = "нен" if is_front else "нан"
                elif ends_with_voiceless:
                    sfx = "тен" if is_front else "тан"
                elif last_ch in "мнң":
                    sfx = "нен" if is_front else "нан"
                else:
                    sfx = "ден" if is_front else "дан"
                cur += sfx

            elif tag == "GEN":
                if ends_with_vowel or last_ch in "рлйу":
                    sfx = "нің" if is_front else "ның"
                elif ends_with_voiceless:
                    sfx = "тің" if is_front else "тың"
                else:
                    sfx = "дің" if is_front else "дың"
                cur += sfx

            elif tag == "INS":
                if ends_with_vowel or last_ch in "рлйумнң":
                    sfx = "мен"
                elif last_ch in "жз":
                    sfx = "бен"
                else:
                    sfx = "пен"
                cur += sfx

        return cur

    @classmethod
    def transfer_affixes(
        cls,
        wrong_word: str,
        wrong_stem: str,
        approved_term: str,
    ) -> str:
        """Transfer grammatical affixes from wrong_word to approved_term."""
        tags = cls.analyze_affixes(wrong_word, wrong_stem)
        return cls.inflect(approved_term, tags)
