from __future__ import annotations

import csv
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from locqa.models import ArbFile


@dataclass
class GlossaryEntry:
    term_ru: str
    term_kk: str
    term_en: str
    comment: str = ""
    status: str = "approved"  # approved | needs_review


class Glossary:
    """Manages the localization terminology glossary (glossary.csv)."""

    def __init__(self, entries: Optional[List[GlossaryEntry]] = None):
        self.entries: List[GlossaryEntry] = entries or []
        self._index_ru: Dict[str, GlossaryEntry] = {}
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._index_ru = {e.term_ru.lower(): e for e in self.entries}

    def add_entry(self, entry: GlossaryEntry) -> None:
        self.entries.append(entry)
        self._index_ru[entry.term_ru.lower()] = entry

    def get_by_ru(self, term_ru: str) -> Optional[GlossaryEntry]:
        return self._index_ru.get(term_ru.lower())

    @classmethod
    def load_csv(cls, path: str) -> Glossary:
        entries: List[GlossaryEntry] = []
        if not os.path.exists(path):
            return cls(entries)

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ru = row.get("term_ru") or row.get("ru") or row.get("source") or ""
                kk = row.get("term_kk") or row.get("kk") or row.get("target") or ""
                en = row.get("term_en") or row.get("en") or ""
                comment = row.get("comment") or row.get("notes") or ""
                status = row.get("status") or "approved"

                if ru.strip():
                    entries.append(
                        GlossaryEntry(
                            term_ru=ru.strip(),
                            term_kk=kk.strip(),
                            term_en=en.strip(),
                            comment=comment.strip(),
                            status=status.strip(),
                        )
                    )

        return cls(entries)

    def save_csv(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        fieldnames = ["term_ru", "term_kk", "term_en", "comment", "status"]
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for e in self.entries:
                writer.writerow({
                    "term_ru": e.term_ru,
                    "term_kk": e.term_kk,
                    "term_en": e.term_en,
                    "comment": e.comment,
                    "status": e.status,
                })


class GlossaryBuilder:
    """Automatically constructs an enriched glossary from parallel ARB files.
    
    Extracts terms dynamically using frequency analysis and parallel alignment across
    source, target, and optional reference files without hardcoded target translations.
    """

    # High-level game entity concepts from specification
    CORE_TERMS_SEED = [
        ("фракция", "Организация / фракция в ролевой игре"),
        ("семья", "Игровой клан / объединение игроков"),
        ("бизнес", "Коммерческое предприятие игрока (АЗС, магазин)"),
        ("Grand Coins", "Премиальная донат-валюта"),
        ("варн", "Игровое предупреждение (warn) за нарушение правил"),
        ("мут", "Блокировка чата игрока (mute)"),
        ("фура", "Грузовой автомобиль для работы дальнобойщика"),
        ("ГК", "Сокращение от Grand Coins"),
        ("донат", "Пополнение счета за реальные деньги"),
        ("промокод", "Бонусный код активации"),
        ("сервер", "Игровой сервер"),
        ("пропуск", "Battle Pass / боевой пропуск"),
        ("рулетка", "Внутриигровая рулетка с призами"),
        ("инкассатор", "Профессия инкассатора"),
        ("аккаунт", "Учетная запись игрока"),
        ("кабинет", "Личный кабинет игрока"),
        ("гараж", "Место хранения транспорта"),
        ("скидка", "Снижение цены в магазине или акции"),
        ("ранг", "Уровень во фракции или рейтинге"),
        ("награда", "Приз за задание или достижение"),
    ]

    @classmethod
    def build_from_arb(
        cls,
        ru_arb: ArbFile,
        kk_arb: ArbFile,
        en_arb: Optional[ArbFile] = None,
    ) -> Glossary:
        glossary = Glossary()

        for term_ru, comment in cls.CORE_TERMS_SEED:
            term_pattern = re.compile(rf"\b{re.escape(term_ru)}\b", re.IGNORECASE)

            # Find matching keys in RU
            matching_keys = [
                k for k, e in ru_arb.entries.items() if term_pattern.search(e.value)
            ]

            kk_candidates: Counter[str] = Counter()
            en_candidates: Counter[str] = Counter()

            for k in matching_keys:
                src_val = ru_arb.get_value(k, "").strip()
                is_direct_key = src_val.lower() == term_ru.lower()

                tgt_val = kk_arb.get_value(k)
                if tgt_val:
                    cleaned_kk = re.sub(r"\{[a-zA-Z0-9_]+\}|<[^>]+>", "", tgt_val).strip()
                    if is_direct_key:
                        kk_candidates[cleaned_kk] += 10
                    elif len(cleaned_kk.split()) <= 2:
                        kk_candidates[cleaned_kk] += 2

                if en_arb:
                    en_val = en_arb.get_value(k)
                    if en_val:
                        cleaned_en = re.sub(r"\{[a-zA-Z0-9_]+\}|<[^>]+>", "", en_val).strip()
                        if is_direct_key:
                            en_candidates[cleaned_en] += 10
                        elif len(cleaned_en.split()) <= 2:
                            en_candidates[cleaned_en] += 2

            # Determine dominant target translation purely from empirical data
            if kk_candidates:
                best_kk = kk_candidates.most_common(1)[0][0]
                status = "approved"
            else:
                best_kk = term_ru
                status = "needs_review"

            if en_candidates:
                best_en = en_candidates.most_common(1)[0][0]
            else:
                best_en = term_ru

            # Normalize term casing in dictionary: keep acronyms/proper names, lowercase ordinary nouns
            def normalize_term_casing(term: str) -> str:
                t = term.strip()
                if not t:
                    return ""
                # If short acronym (<= 3 chars, e.g. GC, ГК), keep uppercase
                if len(t) <= 3 and t.isupper():
                    return t
                # If multi-word brand like Grand Coins, keep Title Case
                if any(w in t.lower() for w in ("grand", "coins", "pass")):
                    return t.title()
                # Otherwise standard lowercase
                return t.lower()

            clean_kk = normalize_term_casing(best_kk)
            clean_en = normalize_term_casing(best_en)
            clean_ru = normalize_term_casing(term_ru)

            glossary.add_entry(
                GlossaryEntry(
                    term_ru=clean_ru,
                    term_kk=clean_kk,
                    term_en=clean_en,
                    comment=comment,
                    status=status,
                )
            )

        return glossary
