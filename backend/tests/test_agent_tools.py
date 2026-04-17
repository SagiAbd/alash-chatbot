import unittest
from unittest.mock import patch

from app.services.agent.tools import _rank_term_matches


class AgentToolsTests(unittest.TestCase):
    def test_rank_term_matches_runs_expensive_scoring_only_for_shortlist(self) -> None:
        """Deep scoring should run only on the top cheap-score candidates."""

        term_rows = [
            (
                "Chunk A",
                {
                    "alash_term": "Term A",
                    "modern_term": "",
                    "author": "Author",
                    "field": "Field",
                    "context": "Context A",
                    "page_content": "Page A",
                },
            ),
            (
                "Chunk B",
                {
                    "alash_term": "Term B",
                    "modern_term": "",
                    "author": "Author",
                    "field": "Field",
                    "context": "Context B",
                    "page_content": "Page B",
                },
            ),
            (
                "Chunk C",
                {
                    "alash_term": "Term C",
                    "modern_term": "",
                    "author": "Author",
                    "field": "Field",
                    "context": "Context C",
                    "page_content": "Page C",
                },
            ),
        ]

        cheap_scores = {
            "Term A": 30,
            "Term B": 20,
            "Term C": 10,
        }
        expensive_contexts: list[str] = []

        def fake_score_match(
            query: str,
            primary_fields: list[str],
            secondary_fields: list[str] | None = None,
        ) -> int:
            del query
            secondary_fields = secondary_fields or []
            if primary_fields:
                return cheap_scores.get(primary_fields[0], 0)

            expensive_contexts.append(secondary_fields[0])
            return 1

        with patch(
            "app.services.agent.tools._score_match",
            side_effect=fake_score_match,
        ):
            ranked = _rank_term_matches(
                term_rows,
                query="term",
                candidate_limit=2,
            )

        self.assertEqual(2, len(ranked))
        self.assertEqual(["Context A", "Context B"], expensive_contexts)

    def test_rank_term_matches_uses_expensive_score_to_reorder_shortlist(self) -> None:
        """Deep scoring should refine ranking among shortlisted cheap matches."""

        term_rows = [
            (
                "Chunk A",
                {
                    "alash_term": "Term A",
                    "modern_term": "",
                    "author": "Author",
                    "field": "Field",
                    "context": "Context A",
                    "page_content": "Page A",
                },
            ),
            (
                "Chunk B",
                {
                    "alash_term": "Term B",
                    "modern_term": "",
                    "author": "Author",
                    "field": "Field",
                    "context": "Context B",
                    "page_content": "Page B",
                },
            ),
        ]

        def fake_score_match(
            query: str,
            primary_fields: list[str],
            secondary_fields: list[str] | None = None,
        ) -> int:
            del query
            secondary_fields = secondary_fields or []
            if primary_fields:
                return {"Term A": 20, "Term B": 18}.get(primary_fields[0], 0)

            return {"Context A": 0, "Context B": 5}.get(secondary_fields[0], 0)

        with patch(
            "app.services.agent.tools._score_match",
            side_effect=fake_score_match,
        ):
            ranked = _rank_term_matches(term_rows, query="term")

        self.assertEqual("Term B", ranked[0][1]["alash_term"])
        self.assertEqual("Term A", ranked[1][1]["alash_term"])


if __name__ == "__main__":
    unittest.main()
