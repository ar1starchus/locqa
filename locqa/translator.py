from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Set

from locqa.models import ArbFile

logger = logging.getLogger(__name__)


class Translator:
    """Provides translation resolution through a 3-tier hierarchy:
    1. Online Translation API (Google Translate gtx or custom API endpoint) with caching and timeout.
    2. Dynamic Cross-ARB Corpus Dictionary (mined from 1-to-1 matching keys in the project ARBs).
    3. Curated UI & Gaming Lexicon (high-precision Kazakh translations for UI words like вокзал, кепки, etc.).
    """

    DEFAULT_API_URL = "https://translate.googleapis.com/translate_a/single?client=gtx&sl={sl}&tl={tl}&dt=t&q={q}"

    # Curated dictionary of common Russian gaming/UI words that should be translated into Kazakh
    BUILTIN_LEXICON: Dict[str, str] = {
        # Transport / Places
        "вокзал": "бекет",
        "автовокзал": "автобекет",
        "аэропорт": "әуежай",
        "остановка": "аялдама",
        "маршрут": "бағыт",
        "багаж": "жүк",
        "багажник": "жүксалғыш",
        "авто": "көлік",
        "машина": "көлік",
        "автомобиль": "автокөлік",
        "грузовик": "жүк көлігі",
        "топливо": "жанармай",

        # Apparel / Accessories
        "кепки": "кепкалар",
        "шапки": "бөріктер",
        "очки": "көзілдірік",
        "одежда": "киім",
        "обувь": "аяқ киім",
        "аксессуары": "аксессуарлар",
        "рюкзак": "арқа қоржын",
        "часы": "сағат",

        # Gaming / Betting / Casino
        "ставка": "бәс",
        "ставки": "бәстер",
        "ничья": "тең",
        "победа": "жеңіс",
        "поражение": "жеңіліс",
        "выигрыш": "ұтыс",
        "проигрыш": "ұтылыс",
        "катушка": "шарғы",
        "леска": "қармақ жібі",
        "крючок": "қармақ",
        "удочка": "қармақ",
        "наживка": "жем",
        "рыбалка": "балық аулау",
        "напугать": "қорқыту",
        "кубок": "тостаған",
        "колода": "үйінді",
        "букет": "гүл шоғы",
        "колба": "шыны сауыт",
        "лента": "таспа",
        "витрина": "сөре",
        "турбонаддув": "турбоүрлеу",
        "клаксоны": "дыбыс белгілері",
        "фейерверк": "отшашу",
        "клоун": "сайқымазақ",

        # UI / Navigation / Economy
        "информация": "ақпарат",
        "правила": "ережелер",
        "настройки": "баптаулар",
        "помощь": "көмек",
        "лимит": "шектеу",
        "лидерборд": "көшбасшылар тақтасы",
        "награда": "марапат",
        "награды": "марапаттар",
        "приз": "жүлде",
        "призы": "жүлделер",
        "магазин": "дүкен",
        "склад": "қойма",
        "рынок": "нарық",
        "задание": "тапсырма",
        "задания": "тапсырмалар",
        "миссия": "миссия",
        "битва": "шайқас",
        "бой": "шайқас",
        "оружие": "қару",
        "патроны": "оқ-дәрілер",
        "броня": "сауыт",
        "здоровье": "денсаулық",
        "деньги": "ақша",
        "баланс": "теңгерім",
        "уровень": "деңгей",
        "опыт": "тәжірибе",
        "город": "қала",
        "дом": "үй",
        "квартира": "пәтер",
        "семья": "отбасы",
        "достар": "достар",
        "сообщения": "хабарламалар",
        "уведомления": "хабарландырулар",
        "почта": "пошта",
        "подарок": "сыйлық",
        "подарки": "сыйлықтар",
        "время": "уақыт",
        "секунда": "секунд",
        "минута": "минут",
        "сағат": "сағат",

        # Legitimate game/UI loanwords that legitimately stay identical across RU and KK
        "тюнинг": "тюнинг",
        "чип-тюнинг": "чип-тюнинг",
        "капот": "капот",
        "бампер": "бампер",
        "неон": "неон",
        "нитро": "нитро",
        "спойлер": "спойлер",
        "стерео": "стерео",
        "стандарт": "стандарт",
        "модификация": "модификация",
        "инвентарь": "инвентарь",
        "профиль": "профиль",
        "дилер": "дилер",
        "сервер": "сервер",
        "контейнер": "контейнер",
        "терминал": "терминал",
        "паспорт": "паспорт",
        "телефон": "телефон",
        "планшет": "планшет",
        "арена": "арена",
        "аукцион": "аукцион",
        "бонус": "бонус",
        "прогресс": "прогресс",
        "чемпионат": "чемпионат",
        "сканер": "сканер",
        "фестиваль": "фестиваль",
        "математика": "математика",
        "информатика": "информатика",
        "физика": "физика",
        "география": "география",
        "биология": "биология",
    }

    def __init__(
        self,
        api_url: Optional[str] = None,
        timeout: float = 2.0,
        enable_online: bool = True,
    ):
        self.api_url = api_url or os.environ.get("TRANSLATE_API_URL")
        self.timeout = timeout
        self.enable_online = enable_online
        self._online_available: bool = enable_online
        self._cache: Dict[str, Optional[str]] = {}
        self._corpus_dict: Optional[Dict[str, str]] = None

    def translate_online(self, text: str, src: str = "ru", tgt: str = "kk") -> Optional[str]:
        """Queries online translation API with timeout and graceful offline fallback."""
        if not self._online_available:
            return None

        clean_text = text.strip()
        cache_key = f"{src}:{tgt}:{clean_text.lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            if self.api_url:
                url = self.api_url.format(sl=src, tl=tgt, q=urllib.parse.quote(clean_text))
            else:
                url = self.DEFAULT_API_URL.format(sl=src, tl=tgt, q=urllib.parse.quote(clean_text))

            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                },
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
                if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                    segments = []
                    for seg in data[0]:
                        if seg and isinstance(seg, list) and len(seg) > 0 and isinstance(seg[0], str):
                            segments.append(seg[0])
                    res = "".join(segments).strip()
                    if res:
                        self._cache[cache_key] = res
                        return res
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            # Network unreachable / DNS failure / timeout -> disable online calls for remaining run
            logger.debug("Translation API unreachable (%s). Falling back to offline lexicon.", e)
            self._online_available = False
        except Exception as e:
            logger.debug("Translation API error: %s", e)

        self._cache[cache_key] = None
        return None

    def build_corpus_dictionary(self, source: ArbFile, target: ArbFile) -> Dict[str, str]:
        """Extracts single-word translation mappings from matching keys across source and target."""
        if self._corpus_dict is not None:
            return self._corpus_dict

        corpus: Dict[str, str] = {}
        for key, src_entry in source.entries.items():
            tgt_entry = target.entries.get(key)
            if tgt_entry is None:
                continue

            s = re.sub(r"\{[a-zA-Z0-9_]+\}|<[^>]+>", " ", src_entry.value).strip()
            t = re.sub(r"\{[a-zA-Z0-9_]+\}|<[^>]+>", " ", tgt_entry.value).strip()

            # Only look for single-word translations
            if " " not in s and " " not in t and len(s) >= 2 and len(t) >= 2:
                if s.lower() != t.lower():
                    corpus[s.lower()] = t

        self._corpus_dict = corpus
        return corpus

    @staticmethod
    def adapt_casing(candidate: str, original: str) -> str:
        """Adapts the grammatical casing of the candidate translation to match the original word.
        - ALL CAPS ('ВОКЗАЛ' -> 'БЕКЕТ', 'КЛАКСОНЫ' -> 'ДЫБЫС БЕЛГІЛЕРІ')
        - Title / Sentence Case ('Кепки' -> 'Кепкалар', 'Колба' -> 'Шыны сауыт')
        - lowercase ('багаж' -> 'жүк')
        - Preserves terminal punctuation ('Лимит:' -> 'Шектеу:')
        """
        orig_clean = original.strip()
        cand_clean = candidate.strip()

        if orig_clean.isupper():
            res = cand_clean.upper()
        elif orig_clean.istitle() or (len(orig_clean) > 0 and orig_clean[0].isupper()):
            # Capitalize first letter of phrase, preserve rest
            if len(cand_clean) <= 1:
                res = cand_clean.upper()
            else:
                res = cand_clean[0].upper() + cand_clean[1:]
        elif orig_clean.islower():
            res = cand_clean.lower()
        else:
            res = cand_clean

        # Preserve terminal punctuation if present in original
        if orig_clean and orig_clean[-1] in "!?.:;" and not res.endswith(orig_clean[-1]):
            res += orig_clean[-1]

        return res

    def translate_term(
        self,
        word: str,
        source: Optional[ArbFile] = None,
        target: Optional[ArbFile] = None,
    ) -> Optional[str]:
        """Resolves the translation for a single term using the 3-tier hierarchy.
        Returns the case-adapted Kazakh translation, or None if the word translates
        identically or no translation is available.
        """
        w = word.strip()
        if not w:
            return None

        clean_w = re.sub(r"\{[a-zA-Z0-9_]+\}|<[^>]+>|[\W_]+", "", w)
        if not clean_w:
            return None

        w_lower = clean_w.lower()
        candidate: Optional[str] = None

        # Tier 1: Online Translation API (if enabled and network is reachable)
        online_res = self.translate_online(clean_w, src="ru", tgt="kk")
        if online_res and online_res.lower() != w_lower:
            candidate = online_res

        # Tier 2: Built-in Curated UI/Game Lexicon (highest offline priority)
        if not candidate and w_lower in self.BUILTIN_LEXICON:
            cand = self.BUILTIN_LEXICON[w_lower]
            if cand.lower() == w_lower:
                # Explicitly marked as loanword that stays identical
                return None
            candidate = cand

        # Tier 3: Dynamic ARB Corpus Dictionary (from other keys in the project)
        if not candidate and source is not None and target is not None:
            corpus = self.build_corpus_dictionary(source, target)
            if w_lower in corpus:
                cand = corpus[w_lower]
                if cand.lower() != w_lower:
                    candidate = cand

        if candidate:
            # Check that it's genuinely different from the source
            if candidate.strip().lower() == w_lower:
                return None
            return self.adapt_casing(candidate, w)

        return None
