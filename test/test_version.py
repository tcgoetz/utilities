"""Test version."""

__author__ = "Philippe Auriach"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"


import unittest

import idbutils


class TestVersion(unittest.TestCase):

    def test_to_string(self):
        self.assertEqual(idbutils.version.to_string((3, 14, 7)), '3.14.7')

    def test_to_string_prerelease(self):
        self.assertEqual(idbutils.version.to_string((4, 0, 0), prerelease=True), '4.0.0 pre')


if __name__ == '__main__':
    unittest.main(verbosity=2)
