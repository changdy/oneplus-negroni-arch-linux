#!/usr/bin/env python3
"""Exercise the default-locale check against a real small ext4 image."""
import unittest

from image_delivery import ImageTest, load_verifier

verifier = load_verifier("locale")


class LocaleImageTests(ImageTest):
    def setUp(self):
        super().setUp()
        self.source("etc/locale.conf", "config/locale/locale.conf")
        self.put("etc/locale.gen", b"en_US.UTF-8 UTF-8\nzh_CN.UTF-8 UTF-8\n")
        self.put("usr/lib/locale/locale-archive", b"fixture: zh_CN.utf8\n")

    def verify(self):
        self.image()
        return verifier.verify(self.base, self.logs)

    def test_default_chinese_locale_is_delivered(self):
        self.verify()

    def test_missing_generated_locale_is_rejected(self):
        self.put("usr/lib/locale/locale-archive", b"fixture: en_US.utf8\n")
        with self.assertRaisesRegex(RuntimeError, "zh_CN.utf8"):
            self.verify()

    def test_english_default_is_rejected(self):
        self.put("etc/locale.conf", b"LANG=en_US.UTF-8\n")
        with self.assertRaisesRegex(RuntimeError, "locale.conf"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
