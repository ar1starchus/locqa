from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
import urllib.request
from collections import Counter
from typing import Any, Dict, Optional, Set, Tuple

from locqa.models import ArbFile

logger = logging.getLogger(__name__)


class Translator:
    """Provides translation resolution through automated, data-driven mechanisms:
    1. Dynamic Cross-ARB Corpus Mining (empirically extracted alignment from parallel ARB entries).
    2. External Translation API Client with persistent JSON caching (no hardcoded python dictionaries).
    """

    DEFAULT_API_URL = "https://translate.googleapis.com/translate_a/single?client=dict-chrome-ex&sl={sl}&tl={tl}&dt=t&q={q}"
    DEFAULT_CACHE_PATH = os.path.join(os.path.dirname(__file__), "data", "translations_cache.json")

    def __init__(
        self,
        api_url: Optional[str] = None,
        cache_path: Optional[str] = None,
        timeout: float = 2.0,
        enable_online: bool = True,
    ):
        self.api_url = api_url or os.environ.get("TRANSLATE_API_URL")
        self.cache_path = cache_path or self.DEFAULT_CACHE_PATH
        self.timeout = timeout
        self.enable_online = enable_online
        self._online_available: bool = enable_online
        self._cache: Dict[str, Optional[str]] = self._load_cache()
        self._corpus_dict: Optional[Dict[str, str]] = None

    def _load_cache(self) -> Dict[str, Optional[str]]:
        """Loads cached API translations from persistent disk storage."""
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception as e:
                logger.debug("Failed to load translation cache from %s: %s", self.cache_path, e)
        return {}

    def _save_cache(self) -> None:
        """Persists translation cache to disk for offline environments."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.cache_path)), exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug("Failed to save translation cache to %s: %s", self.cache_path, e)

    def translate_online(self, text: str, src: str = "ru", tgt: str = "kk") -> Optional[str]:
        """Queries online translation API with timeout and graceful offline fallback."""
        if not self._online_available:
            return None

        clean_text = text.strip()
        if not clean_text:
            return None

        cache_key = clean_text.lower()
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
                        self._save_cache()
                        return res
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            logger.debug("Translation API unreachable (%s). Falling back to offline corpus/cache.", e)
            self._online_available = False
        except Exception as e:
            logger.debug("Translation API error: %s", e)

        return None

    def build_corpus_dictionary(
        self,
        source: ArbFile,
        target: ArbFile,
    ) -> Dict[str, str]:
        """Dynamically extracts single-word and short phrase translations
        by aligning parallel keys across source and target ARB files.
        100% automated and data-driven from project localization files.
        """
        if self._corpus_dict is not None:
            return self._corpus_dict

        pair_counts: Counter[Tuple[str, str]] = Counter()

        for key, src_entry in source.entries.items():
            tgt_entry = target.entries.get(key)
            if tgt_entry is None:
                continue

            s = re.sub(r"\{[a-zA-Z0-9_]+\}|<[^>]+>", " ", src_entry.value).strip()
            t = re.sub(r"\{[a-zA-Z0-9_]+\}|<[^>]+>", " ", tgt_entry.value).strip()

            s_words = s.split()
            t_words = t.split()

            # 1-to-1 exact single word mappings (e.g. 'Информация' -> 'Ақпарат', 'Помощь' -> 'Көмек')
            if len(s_words) == 1 and len(t_words) == 1:
                s_low = s_words[0].lower()
                t_val = t_words[0]
                if s_low != t_val.lower() and len(s_low) >= 3 and len(t_val) >= 3:
                    pair_counts[(s_low, t_val)] += 10
            # 1-to-2 mappings (e.g. 'Назад' -> 'Кері қайту')
            elif len(s_words) == 1 and len(t_words) == 2:
                s_low = s_words[0].lower()
                t_val = " ".join(t_words)
                if s_low != t_val.lower() and len(s_low) >= 3:
                    pair_counts[(s_low, t_val)] += 5

        # Take the most frequent target translation for each source term
        grouped: Dict[str, Counter[str]] = {}
        for (src_w, tgt_w), count in pair_counts.items():
            if src_w not in grouped:
                grouped[src_w] = Counter()
            grouped[src_w][tgt_w] += count

        corpus: Dict[str, str] = {}
        for src_w, candidates in grouped.items():
            best_trans, count = candidates.most_common(1)[0]
            # Require minimum confidence threshold to prevent picking up one-off translator typos
            if count >= 15:
                corpus[src_w] = best_trans

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
            if len(cand_clean) <= 1:
                res = cand_clean.upper()
            else:
                res = cand_clean[0].upper() + cand_clean[1:]
        elif orig_clean.islower():
            res = cand_clean.lower()
        else:
            res = cand_clean

        if orig_clean and orig_clean[-1] in "!?.:;" and not res.endswith(orig_clean[-1]):
            res += orig_clean[-1]

        return res

    def translate_term(
        self,
        word: str,
        source: Optional[ArbFile] = None,
        target: Optional[ArbFile] = None,
    ) -> Optional[str]:
        """Resolves the translation for a single term without hardcoded lexicons:
        1. Dynamic ARB Corpus alignment (mined on the fly from project ARBs).
        2. Persistent Translation Cache / Online Translation API.
        """
        w = word.strip()
        if not w:
            return None

        clean_w = re.sub(r"\{[a-zA-Z0-9_]+\}|<[^>]+>|[\W_]+", "", w)
        if not clean_w:
            return None

        w_lower = clean_w.lower()
        candidate: Optional[str] = None

        # Tier 1: Dynamic ARB Corpus alignment (highest domain fidelity)
        if source is not None and target is not None:
            corpus = self.build_corpus_dictionary(source, target)
            if w_lower in corpus:
                cand = corpus[w_lower]
                if cand.lower() != w_lower:
                    candidate = cand

        # Tier 2: Persistent Translation Cache / Online Translation API
        if not candidate:
            cached_res = self._cache.get(w_lower)
            if cached_res is not None:
                if cached_res.lower() != w_lower:
                    candidate = cached_res
            elif self._online_available:
                online_res = self.translate_online(clean_w, src="ru", tgt="kk")
                if online_res and online_res.lower() != w_lower:
                    candidate = online_res

        if candidate:
            if candidate.strip().lower() == w_lower:
                return None
            return self.adapt_casing(candidate, w)

        return None

    def sync_translations_for_arb(self, source: ArbFile, target: ArbFile) -> int:
        """Pre-warms the translation cache for all untranslated single words
        by querying the Translation API and saving the results.
        """
        words_to_sync: Set[str] = set()
        for key, src_entry in source.entries.items():
            tgt_entry = target.entries.get(key)
            if tgt_entry is None or src_entry.value.strip() != tgt_entry.value.strip():
                continue
            clean = re.sub(r"\{[a-zA-Z0-9_]+\}|<[^>]+>", "", src_entry.value).strip()
            if " " not in clean and len(clean) > 1 and re.match(r"^[а-яА-ЯёЁәіңғүұқөһӘІҢҒҮҰҚӨҺ\-]+$", clean):
                words_to_sync.add(clean.lower())

        count = 0
        for w in sorted(words_to_sync):
            if w not in self._cache and self._online_available:
                res = self.translate_online(w, src="ru", tgt="kk")
                if res:
                    count += 1
        if count > 0:
            self._save_cache()
        return count
