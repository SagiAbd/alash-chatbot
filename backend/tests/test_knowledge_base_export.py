import unittest

from app.api.api_v1.knowledge_base import (
    _build_chunk_hash,
    _build_imported_chunk_id,
    _build_imported_chunk_metadata,
    _sanitize_export_file_name,
)


class KnowledgeBaseExportHelpersTest(unittest.TestCase):
    def test_build_imported_chunk_metadata_repoints_ids(self) -> None:
        metadata = {
            "page_content": "Example text",
            "kb_id": 1,
            "document_id": 2,
            "chunk_id": "old",
            "work_title": "Example work",
        }

        updated = _build_imported_chunk_metadata(metadata, 10, 20, "new")

        self.assertEqual(updated["kb_id"], 10)
        self.assertEqual(updated["document_id"], 20)
        self.assertEqual(updated["chunk_id"], "new")
        self.assertEqual(updated["work_title"], "Example work")
        self.assertEqual(metadata["kb_id"], 1)

    def test_build_imported_chunk_id_is_deterministic_and_scoped(self) -> None:
        first = _build_imported_chunk_id(5, 6, "chunk-a")
        second = _build_imported_chunk_id(5, 6, "chunk-a")
        different = _build_imported_chunk_id(7, 6, "chunk-a")

        self.assertEqual(first, second)
        self.assertNotEqual(first, different)

    def test_build_chunk_hash_changes_when_metadata_changes(self) -> None:
        metadata = {"page_content": "Example text", "page_number": 12}
        same_hash = _build_chunk_hash(metadata)
        changed_hash = _build_chunk_hash(
            {"page_content": "Example text", "page_number": 13}
        )

        self.assertEqual(same_hash, _build_chunk_hash(metadata))
        self.assertNotEqual(same_hash, changed_hash)

    def test_sanitize_export_file_name(self) -> None:
        self.assertEqual(
            _sanitize_export_file_name("Alash / KB", 4),
            "Alash_KB.json",
        )
        self.assertEqual(
            _sanitize_export_file_name("   ", 4),
            "knowledge-base-4.json",
        )


if __name__ == "__main__":
    unittest.main()
