import unittest

from app.services.agent.agent import _SYSTEM_PROMPT


class AgentPromptTests(unittest.TestCase):
    def test_alash_style_requests_require_figure_identification(self) -> None:
        """Style requests should identify which Alash figure is intended."""

        self.assertIn('"Алаш стилінде"', _SYSTEM_PROMPT)
        self.assertIn("алдымен нақты қай қайраткердің", _SYSTEM_PROMPT)

    def test_alash_style_requests_allow_clarification_when_ambiguous(self) -> None:
        """Ambiguous style requests should trigger a short clarification."""

        self.assertIn("қысқа нақтылаушы сұрақ", _SYSTEM_PROMPT)
        self.assertIn("стильдік сұрауда", _SYSTEM_PROMPT)

    def test_alash_style_requests_require_reading_multiple_works(self) -> None:
        """The prompt should require reading several works before imitation."""

        self.assertIn("кемінде 2-3 релевант шығарманың мәтінін оқыңыз", _SYSTEM_PROMPT)
        self.assertIn(
            "бірнеше мәтінін оқымай тұрып еліктеуге кіріспеңіз",
            _SYSTEM_PROMPT,
        )


if __name__ == "__main__":
    unittest.main()
