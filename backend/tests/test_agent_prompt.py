import unittest

from app.services.agent.agent import _SYSTEM_PROMPT


class AgentPromptTests(unittest.TestCase):
    def test_raw_page_tool_is_read_pages_only(self) -> None:
        """The prompt should expose raw pages as a read-only verification tool."""

        self.assertIn("`read_pages`", _SYSTEM_PROMPT)
        self.assertNotIn("`search_pages`", _SYSTEM_PROMPT)
        self.assertIn("тек нақты беттерді оқу үшін", _SYSTEM_PROMPT)

    def test_alash_style_requests_require_figure_identification(self) -> None:
        """Style requests should identify which Alash figure is intended."""

        self.assertIn("Алаш стилінде", _SYSTEM_PROMPT)
        self.assertIn("Стиль иесі анық болмаса", _SYSTEM_PROMPT)

    def test_alash_style_requests_allow_clarification_when_ambiguous(self) -> None:
        """Ambiguous style requests should trigger a short clarification."""

        self.assertIn("қысқа нақтылау сұрағын", _SYSTEM_PROMPT)
        self.assertIn("СТИЛЬДІК СҰРАУ", _SYSTEM_PROMPT)

    def test_alash_style_requests_require_reading_multiple_works(self) -> None:
        """The prompt should require reading several works before imitation."""

        self.assertIn("сол автордың 2–3 шығармасын оқып шығыңыз", _SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
