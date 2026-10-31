import unittest
import os
import tempfile

from locqa.models import ArbFile, ArbEntry, IssueType, Severity
from locqa.parser import ArbParser
from locqa.checkers.untranslated import UntranslatedChecker
from locqa.checkers.same_as_source import SameAsSourceChecker
from locqa.checkers.placeholder import PlaceholderChecker
from locqa.checkers.plural import PluralChecker
from locqa.checkers.length import LengthOverflowChecker
from locqa.checkers.suffix_harmony import SuffixHarmonyChecker
from locqa.checkers.orthography import OrthographyChecker
from locqa.checkers.wrong_language import WrongLanguageChecker
from locqa.checkers.inconsistent_term import InconsistentTermChecker
from locqa.checkers.glossary import GlossaryChecker
from locqa.glossary import Glossary, GlossaryEntry
from locqa.transliteration import KazakhLatinTransliteration
from locqa.fixer import ArbFixer


class TestArbParser(unittest.TestCase):
    def test_parse_and_write_roundtrip(self):
        sample_arb = """{
  "@@locale": "kk",
  "@@comment": "SECTION_A",
  "hello": "Сәлем",
  "@hello": {
    "description": "Greeting"
  },
  "@@comment": "SECTION_B",
  "world": "Әлем"
}"""
        parsed = ArbParser.parse_content(sample_arb)
        self.assertEqual(parsed.locale, "kk")
        self.assertEqual(len(parsed.entries), 2)
        self.assertEqual(parsed.get_value("hello"), "Сәлем")
        self.assertEqual(len(parsed.sections), 2)
        self.assertIn("hello", parsed.metadata)

        # Test write
        with tempfile.NamedTemporaryFile("w+", suffix=".arb", delete=False) as tf:
            path = tf.name
        try:
            ArbParser.write_file(parsed, path, replacements={"hello": "Амансың ба"})
            reparsed = ArbParser.parse_file(path)
            self.assertEqual(reparsed.get_value("hello"), "Амансың ба")
            self.assertEqual(reparsed.get_value("world"), "Әлем")
        finally:
            if os.path.exists(path):
                os.remove(path)


class TestCheckers(unittest.TestCase):
    def test_untranslated(self):
        src = ArbFile(path="", locale="ru", entries={
            "k1": ArbEntry(key="k1", value="Текст", raw_line="", line_number=1),
            "k2": ArbEntry(key="k2", value="Кнопка", raw_line="", line_number=2),
        })
        tgt = ArbFile(path="", locale="kk", entries={
            "k1": ArbEntry(key="k1", value="Мәтін", raw_line="", line_number=1),
            "k2": ArbEntry(key="k2", value="   ", raw_line="", line_number=2),  # empty
        })
        findings = UntranslatedChecker().check(src, tgt)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].key, "k2")

    def test_same_as_source(self):
        src = ArbFile(path="", locale="ru", entries={
            "btn_rent": ArbEntry(key="btn_rent", value="Вы действительно хотите продолжить?", raw_line="", line_number=1),
            "brand": ArbEntry(key="brand", value="Grand Mobile", raw_line="", line_number=2),
            "metric_unit": ArbEntry(key="metric_unit", value="{seconds} сек.", raw_line="", line_number=3),
            "loanword": ArbEntry(key="loanword", value="Гараж", raw_line="", line_number=4),
            "street_racing": ArbEntry(key="street_racing", value="Уличные Гонки", raw_line="", line_number=5),
        })
        tgt = ArbFile(path="", locale="kk", entries={
            "btn_rent": ArbEntry(key="btn_rent", value="Вы действительно хотите продолжить?", raw_line="", line_number=1),
            "brand": ArbEntry(key="brand", value="Grand Mobile", raw_line="", line_number=2),
            "metric_unit": ArbEntry(key="metric_unit", value="{seconds} сек.", raw_line="", line_number=3),
            "loanword": ArbEntry(key="loanword", value="Гараж", raw_line="", line_number=4),
            "street_racing": ArbEntry(key="street_racing", value="Уличные Гонки", raw_line="", line_number=5),
        })
        glo = Glossary([GlossaryEntry(term_ru="Гараж", term_kk="Гараж", term_en="Garage")])
        findings = SameAsSourceChecker().check(src, tgt, context={"glossary": glo})
        # 'Grand Mobile' is a brand, '{seconds} сек.' is a metric unit, 'Гараж' is glossary/loanword
        # Only 'btn_rent' and 'street_racing' (Уличные Гонки) have Russian grammar and should be flagged
        flagged_keys = {f.key for f in findings}
        self.assertEqual(flagged_keys, {"btn_rent", "street_racing"})

    def test_same_as_source_single_words_translation(self):
        src = ArbFile(path="", locale="ru", entries={
            "laRailwayStation": ArbEntry(key="laRailwayStation", value="ВОКЗАЛ", raw_line="", line_number=1),
            "accessories_type_caps": ArbEntry(key="accessories_type_caps", value="КЕПКИ", raw_line="", line_number=2),
            "car_trunk": ArbEntry(key="car_trunk", value="багаж", raw_line="", line_number=3),
            "bet": ArbEntry(key="bet", value="Ставка", raw_line="", line_number=4),
            "loanword_hood": ArbEntry(key="loanword_hood", value="Капот", raw_line="", line_number=5),
            "country_brazil": ArbEntry(key="country_brazil", value="Бразилия", raw_line="", line_number=6),
            "glossary_account": ArbEntry(key="glossary_account", value="АККАУНТ", raw_line="", line_number=7),
        })
        tgt = ArbFile(path="", locale="kk", entries={
            "laRailwayStation": ArbEntry(key="laRailwayStation", value="ВОКЗАЛ", raw_line="", line_number=1),
            "accessories_type_caps": ArbEntry(key="accessories_type_caps", value="КЕПКИ", raw_line="", line_number=2),
            "car_trunk": ArbEntry(key="car_trunk", value="багаж", raw_line="", line_number=3),
            "bet": ArbEntry(key="bet", value="Ставка", raw_line="", line_number=4),
            "loanword_hood": ArbEntry(key="loanword_hood", value="Капот", raw_line="", line_number=5),
            "country_brazil": ArbEntry(key="country_brazil", value="Бразилия", raw_line="", line_number=6),
            "glossary_account": ArbEntry(key="glossary_account", value="АККАУНТ", raw_line="", line_number=7),
        })
        glo = Glossary([GlossaryEntry(term_ru="АККАУНТ", term_kk="АККАУНТ", term_en="ACCOUNT")])
        findings = SameAsSourceChecker().check(src, tgt, context={"glossary": glo})

        findings_by_key = {f.key: f for f in findings}
        # ВОКЗАЛ -> БЕКЕТ
        self.assertIn("laRailwayStation", findings_by_key)
        self.assertEqual(findings_by_key["laRailwayStation"].suggestion, "БЕКЕТ")

        # КЕПКИ -> КЕПКАЛАР
        self.assertIn("accessories_type_caps", findings_by_key)
        self.assertEqual(findings_by_key["accessories_type_caps"].suggestion, "КЕПКАЛАР")

        # багаж -> жүк
        self.assertIn("car_trunk", findings_by_key)
        self.assertEqual(findings_by_key["car_trunk"].suggestion, "жүк")

        # Ставка -> Бәс
        self.assertIn("bet", findings_by_key)
        self.assertEqual(findings_by_key["bet"].suggestion, "Бәс")

        # Legitimate matches: Капот (loanword), Бразилия (country), АККАУНТ (glossary) must NOT be flagged
        self.assertNotIn("loanword_hood", findings_by_key)
        self.assertNotIn("country_brazil", findings_by_key)
        self.assertNotIn("glossary_account", findings_by_key)

    def test_translator_casing_and_punctuation(self):
        from locqa.translator import Translator
        self.assertEqual(Translator.adapt_casing("бекет", "ВОКЗАЛ"), "БЕКЕТ")
        self.assertEqual(Translator.adapt_casing("кепкалар", "Кепки"), "Кепкалар")
        self.assertEqual(Translator.adapt_casing("жүк", "багаж"), "жүк")
        self.assertEqual(Translator.adapt_casing("шектеу", "Лимит:"), "Шектеу:")
        self.assertEqual(Translator.adapt_casing("отшашу", "Фейерверк!"), "Отшашу!")

    def test_placeholder_mismatch(self):
        src = ArbFile(path="", locale="ru", entries={
            "k1": ArbEntry(key="k1", value="Уровень {level}", raw_line="", line_number=1),
            "k2": ArbEntry(key="k2", value="Привет {name}", raw_line="", line_number=2),
        })
        tgt = ArbFile(path="", locale="kk", entries={
            "k1": ArbEntry(key="k1", value="Деңгей {leve}", raw_line="", line_number=1),  # typo
            "k2": ArbEntry(key="k2", value="Сәлем", raw_line="", line_number=2),          # missing
        })
        findings = PlaceholderChecker().check(src, tgt)
        self.assertEqual(len(findings), 2)
        # Check that {leve} was corrected to {level} in suggestion
        f1 = [f for f in findings if f.key == "k1"][0]
        self.assertEqual(f1.suggestion, "Деңгей {level}")

    def test_suffix_harmony(self):
        src = ArbFile(path="", locale="ru", entries={
            "k1": ArbEntry(key="k1", value="Купить за {price}", raw_line="", line_number=1),
        })
        tgt = ArbFile(path="", locale="kk", entries={
            "k1": ArbEntry(key="k1", value="{price}-ге сатып алу", raw_line="", line_number=1),
        })
        findings = SuffixHarmonyChecker().check(src, tgt)
        self.assertEqual(len(findings), 1)
        self.assertIn("сомасына", findings[0].suggestion)

    def test_orthography(self):
        src = ArbFile(path="", locale="ru", entries={
            "k1": ArbEntry(key="k1", value="Текст", raw_line="", line_number=1),
            "k2": ArbEntry(key="k2", value="Сезонный пропуск", raw_line="", line_number=2),
            "k3": ArbEntry(key="k3", value="Устроиться в Chicken", raw_line="", line_number=3),
            "k4": ArbEntry(key="k4", value="Ранг в PVP", raw_line="", line_number=4),
        })
        # Latin 'i' inside Cyrillic word, plus valid English words with Kazakh affixes
        tgt = ArbFile(path="", locale="kk", entries={
            "k1": ArbEntry(key="k1", value="бөлімiне өту", raw_line="", line_number=1),
            "k2": ArbEntry(key="k2", value="Season Pass-ты сатып алыңыз", raw_line="", line_number=2),
            "k3": ArbEntry(key="k3", value="GRAND CHICKEN-қа қош келдіңіз!", raw_line="", line_number=3),
            "k4": ArbEntry(key="k4", value="PVP-дегі жеңіс пен VIP-і бар ойыншы", raw_line="", line_number=4),
        })
        findings = OrthographyChecker().check(src, tgt)
        # Only k1 with 'бөлімiне' should be flagged; English words with affixes should NOT be false positives
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].key, "k1")
        self.assertEqual(findings[0].suggestion, "бөліміне өту")

    def test_wrong_language_brand_preservation(self):
        src = ArbFile(path="", locale="ru", entries={
            "telegram": ArbEntry(key="telegram", value="Telegram", raw_line="", line_number=1),
            "app_1xbet": ArbEntry(key="app_1xbet", value="1XBET", raw_line="", line_number=2),
            "err": ArbEntry(key="err", value="Ошибка авторизации", raw_line="", line_number=3),
        })
        tgt = ArbFile(path="", locale="kk", entries={
            "telegram": ArbEntry(key="telegram", value="Telegram", raw_line="", line_number=1),
            "app_1xbet": ArbEntry(key="app_1xbet", value="1XBET", raw_line="", line_number=2),
            "err": ArbEntry(key="err", value="Avtorizatsiya xatosi", raw_line="", line_number=3),
        })
        uz = ArbFile(path="", locale="uz", entries={
            "telegram": ArbEntry(key="telegram", value="Telegram", raw_line="", line_number=1),
            "app_1xbet": ArbEntry(key="app_1xbet", value="1XBET", raw_line="", line_number=2),
            "err": ArbEntry(key="err", value="Avtorizatsiya xatosi", raw_line="", line_number=3),
        })
        findings = WrongLanguageChecker().check(src, tgt, context={"auxiliary_arb_files": {"uz": uz}})
        # Only 'err' should be flagged as Uzbek wrong_language, 'Telegram' and '1XBET' are preserved brands
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].key, "err")
        self.assertIn("узбекском", findings[0].evidence.lower())

    def test_length_overflow(self):
        src = ArbFile(path="", locale="ru", entries={
            "action_btn": ArbEntry(key="action_btn", value="Арендовать", raw_line="", line_number=1),
        })
        tgt = ArbFile(path="", locale="kk", entries={
            "action_btn": ArbEntry(key="action_btn", value="Жалға алу үшін басыңыз және тексеріңіз", raw_line="", line_number=1),
        })
        findings = LengthOverflowChecker().check(src, tgt)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].key, "action_btn")
        self.assertIsNone(findings[0].suggestion)

    def test_transliteration(self):
        text = "Қазақстан, {name} үшін!"
        latin = KazakhLatinTransliteration.transliterate_text(text)
        self.assertEqual(latin, "Qazaqstan, {name} üşin!")

    def test_kazakh_morphological_transfer(self):
        from locqa.morphology import KazakhMorphology

        # 1. Ваша награда -> Сіздің жүлдеңіз
        inflected = KazakhMorphology.transfer_affixes("сыйлығыңыз", "сыйлық", "жүлде")
        self.assertEqual(inflected, "жүлдеңіз")

        # 2. Google аккаунты
        inflected2 = KazakhMorphology.transfer_affixes("тіркелгісі", "тіркелгі", "аккаунт")
        self.assertEqual(inflected2, "аккаунты")

        # 3. Множественное число: сыйлықтар -> жүлделер
        inflected3 = KazakhMorphology.transfer_affixes("сыйлықтар", "сыйлық", "жүлде")
        self.assertEqual(inflected3, "жүлделер")

    def test_glossary_with_morphology(self):
        src = ArbFile(path="", locale="ru", entries={
            "k1": ArbEntry(key="k1", value="Ваша награда", raw_line="", line_number=1),
        })
        tgt = ArbFile(path="", locale="kk", entries={
            "k1": ArbEntry(key="k1", value="Сіздің сыйлығыңыз", raw_line="", line_number=1),
        })
        glo = Glossary([GlossaryEntry(term_ru="награда", term_kk="жүлде", term_en="reward")])
        findings = GlossaryChecker().check(src, tgt, context={"glossary": glo})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].suggestion, "Сіздің жүлдеңіз")

    def test_glossary_casing_target_precedence(self):
        # Russian source has 'Награда' capitalized as first word,
        # but in Kazakh syntax 'сыйлығы' is lowercase in mid-sentence position.
        src = ArbFile(path="", locale="ru", entries={
            "rewardForSubscription": ArbEntry(key="rewardForSubscription", value="Награда за подписку", raw_line="", line_number=1),
        })
        tgt = ArbFile(path="", locale="kk", entries={
            "rewardForSubscription": ArbEntry(key="rewardForSubscription", value="жазылым сыйлығы", raw_line="", line_number=1),
        })
        glo = Glossary([GlossaryEntry(term_ru="награда", term_kk="жүлде", term_en="reward")])
        findings = GlossaryChecker().check(src, tgt, context={"glossary": glo})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].suggestion, "жазылым жүлдесі")

    def test_reporter_html_textarea_newlines(self):
        import tempfile
        from locqa.reporter import Reporter
        from locqa.models import Finding, IssueType, Severity

        multiline_sug = "Жеңімпаз\nбәрін алады!"
        finding = Finding(
            key="testKey",
            issue_type=IssueType.GLOSSARY_VIOLATION,
            severity=Severity.HIGH,
            source="Победитель\nзабирает всё!",
            target="Жеңімпаз\nбәрін сыйлық алады!",
            evidence="тест",
            suggestion=multiline_sug,
            confidence=0.95,
        )
        with tempfile.NamedTemporaryFile("w+", suffix=".html", delete=False) as tmp:
            tmp_path = tmp.name

        Reporter.save_html([finding], tmp_path, target_raw_content='{"testKey": "..."}')
        with open(tmp_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Should render <textarea> preserving newlines, never <input type="text">
        self.assertIn("<textarea class=\"sug-input\"", content)
        self.assertIn("Жеңімпаз\nбәрін алады!", content)
        self.assertNotIn('<input type="text" class="sug-input"', content)


if __name__ == "__main__":
    unittest.main()
