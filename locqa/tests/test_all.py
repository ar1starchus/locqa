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


if __name__ == "__main__":
    unittest.main()
