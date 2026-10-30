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
        })
        tgt = ArbFile(path="", locale="kk", entries={
            "btn_rent": ArbEntry(key="btn_rent", value="Вы действительно хотите продолжить?", raw_line="", line_number=1),
            "brand": ArbEntry(key="brand", value="Grand Mobile", raw_line="", line_number=2),
        })
        findings = SameAsSourceChecker().check(src, tgt)
        # "Grand Mobile" is in whitelist, so only "btn_rent" should be flagged
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].key, "btn_rent")

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
        })
        # Latin 'i' inside Cyrillic word
        tgt = ArbFile(path="", locale="kk", entries={
            "k1": ArbEntry(key="k1", value="бөлімiне өту", raw_line="", line_number=1),
        })
        findings = OrthographyChecker().check(src, tgt)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].suggestion, "бөліміне өту")

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
