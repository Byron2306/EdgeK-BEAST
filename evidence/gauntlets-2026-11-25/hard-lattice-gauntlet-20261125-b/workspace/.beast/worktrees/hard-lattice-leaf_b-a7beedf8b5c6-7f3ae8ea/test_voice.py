import unittest

import voice
from greeter.service import welcome


class VoiceContract(unittest.TestCase):
    def test_direct_contract(self):
        self.assertEqual(voice.greeting(), "hello")

    def test_casual_welcome(self):
        self.assertEqual(welcome("casual"), "hello")

    def test_formal_welcome(self):
        self.assertEqual(welcome("formal"), "Hello")
