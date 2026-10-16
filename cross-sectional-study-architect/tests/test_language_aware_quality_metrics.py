from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from design_common import body_word_count, sequence_uniqueness  # noqa: E402


class LanguageAwareQualityMetricTests(unittest.TestCase):
    def test_chinese_content_is_counted(self):
        text = "这是一个用于研究方案质量门禁的完整中文句子。"
        self.assertGreater(body_word_count(text), 10)

    def test_repeated_chinese_padding_has_low_uniqueness(self):
        repeated = "研究设计数据质量统计分析偏倚控制敏感性分析" * 50
        self.assertLess(sequence_uniqueness(repeated), 0.2)


if __name__ == "__main__":
    unittest.main()
