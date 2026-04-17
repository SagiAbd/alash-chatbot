import unittest
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document as LangchainDocument

from app.services import document_processor
from app.services.book_indexer import (
    BookIndex,
    BookMetadata,
    BookMetadataResult,
    TOCEntry,
    TOCSearchResult,
    WorkEntry,
    build_analysis_input,
    build_metadata_input,
    extract_pages,
    extract_works,
)


def make_page(page_number: int, text: str) -> LangchainDocument:
    """Build a minimal OCR page document for tests."""

    return LangchainDocument(page_content=text, metadata={"page": page_number})


class BookIndexerTests(unittest.TestCase):
    def test_build_document_chunk_id_distinguishes_work_ranges(self) -> None:
        """Work chunk IDs should not collide on shared titles/opening text."""

        shared_text = "Shared opening text. " * 20

        first = document_processor._build_document_chunk_id(
            document_id=11,
            chunk_type="work",
            metadata={
                "work_title": "Repeated Title",
                "start_page": 5,
                "end_page": 20,
            },
            page_content=shared_text,
        )
        second = document_processor._build_document_chunk_id(
            document_id=11,
            chunk_type="work",
            metadata={
                "work_title": "Repeated Title",
                "start_page": 21,
                "end_page": 35,
            },
            page_content=shared_text,
        )

        self.assertNotEqual(first, second)

    def test_build_document_chunk_id_uses_full_content_hash_for_pages(self) -> None:
        """Page chunk IDs should differ when only trailing text changes."""

        shared_prefix = "A" * 220
        first = document_processor._build_document_chunk_id(
            document_id=11,
            chunk_type="page",
            metadata={"page_number": 120},
            page_content=shared_prefix + "first ending",
        )
        second = document_processor._build_document_chunk_id(
            document_id=11,
            chunk_type="page",
            metadata={"page_number": 120},
            page_content=shared_prefix + "second ending",
        )

        self.assertNotEqual(first, second)

    def test_extract_pages_keeps_book_metadata(self) -> None:
        """Page extraction should use the book index metadata, not loop counters."""

        pages = [
            make_page(12, "Page 12 body. " * 4),
            make_page(14, "Page 14 body. " * 4),
        ]
        book_index = BookIndex(
            summary="summary",
            metadata=BookMetadata(book_title="Book", main_author="Author"),
            works=[],
        )

        docs = extract_pages(pages, book_index, "book.json")

        self.assertEqual(2, len(docs))
        self.assertEqual(12, docs[0].metadata["page_number"])
        self.assertEqual(14, docs[1].metadata["page_number"])
        self.assertEqual("Author", docs[0].metadata["main_author"])
        self.assertEqual("Book", docs[0].metadata["book_title"])

    def test_extract_works_uses_padded_actual_page_numbers_for_sparse_ocr(self) -> None:
        """Sparse OCR page sets should use page padding without index drift."""

        pages = [
            make_page(326, "Page 326 body. " * 8),
            make_page(327, "Page 327 body. " * 8),
            make_page(330, "Page 330 body. " * 8),
            make_page(331, "Page 331 body. " * 8),
            make_page(332, "Page 332 body. " * 8),
            make_page(333, "Page 333 body. " * 8),
        ]
        index = BookIndex(
            summary="summary",
            metadata=BookMetadata(book_title="Book", main_author="Author"),
            works=[
                WorkEntry(title="Work One", start_page=327, end_page=327),
                WorkEntry(title="Work Two", start_page=331, end_page=332),
            ],
        )

        docs = extract_works(pages, index, "book.json")

        self.assertEqual(2, len(docs))
        self.assertEqual("Work One", docs[0].metadata["work_title"])
        self.assertIn("Page 326 body.", docs[0].page_content)
        self.assertIn("Page 327 body.", docs[0].page_content)
        self.assertNotIn("Page 330 body.", docs[0].page_content)
        self.assertNotIn("Page 331 body.", docs[0].page_content)
        self.assertEqual("Work Two", docs[1].metadata["work_title"])
        self.assertIn("Page 330 body.", docs[1].page_content)
        self.assertIn("Page 331 body.", docs[1].page_content)
        self.assertIn("Page 332 body.", docs[1].page_content)
        self.assertIn("Page 333 body.", docs[1].page_content)
        self.assertNotIn("Page 327 body.", docs[1].page_content)

    def test_build_analysis_input_marks_candidate_toc_pages(self) -> None:
        """LLM input should expose candidate TOC pages as a separate section."""

        pages = [
            make_page(5, "Мазмұны\nБірінші бөлім .... 10\nЕкінші бөлім .... 20"),
            make_page(6, "Үшінші бөлім .... 30\nТөртінші бөлім .... 40"),
            make_page(7, "Actual work body. " * 8),
        ]

        analysis_input = build_analysis_input(pages)

        self.assertIn("Candidate TOC pages:", analysis_input)
        self.assertIn("--- Page 5 ---", analysis_input)
        self.assertIn("--- Page 6 ---", analysis_input)
        self.assertIn("Мазмұны", analysis_input)
        self.assertNotIn("First pages:", analysis_input)
        self.assertNotIn("Last pages:", analysis_input)

    def test_build_metadata_input_uses_first_and_last_context(self) -> None:
        """Metadata extraction should keep the original first/last context read."""

        pages = [make_page(page, f"Body {page}") for page in range(1, 8)]

        metadata_input = build_metadata_input(pages)

        self.assertIn("First pages:", metadata_input)
        self.assertIn("Last pages:", metadata_input)
        self.assertIn("--- Page 1 ---", metadata_input)
        self.assertIn("--- Page 3 ---", metadata_input)
        self.assertIn("--- Page 6 ---", metadata_input)
        self.assertIn("--- Page 7 ---", metadata_input)

    def test_build_analysis_input_uses_last_page_window_when_requested(self) -> None:
        """Fallback mode should expose the trailing page window to the LLM."""

        pages = [make_page(page, f"Body {page}") for page in range(1, 21)]

        analysis_input = build_analysis_input(pages, mode="last_pages", window_size=15)

        self.assertIn("Last 15 pages:", analysis_input)
        self.assertIn("--- Page 6 ---", analysis_input)
        self.assertIn("--- Page 20 ---", analysis_input)
        self.assertNotIn("--- Page 5 ---\nBody 5", analysis_input)
        self.assertNotIn("First pages:", analysis_input)

    def test_build_analysis_input_uses_first_page_window_when_requested(self) -> None:
        """Final fallback mode should expose the leading page window to the LLM."""

        pages = [make_page(page, f"Body {page}") for page in range(1, 21)]

        analysis_input = build_analysis_input(pages, mode="first_pages", window_size=15)

        self.assertIn("First 15 pages:", analysis_input)
        self.assertIn("--- Page 1 ---", analysis_input)
        self.assertIn("--- Page 15 ---", analysis_input)
        self.assertNotIn("--- Page 16 ---\nBody 16", analysis_input)
        self.assertNotIn("Last pages:", analysis_input)

    @patch("app.services.document_processor.extract_pages")
    @patch("app.services.document_processor.extract_works")
    @patch("app.services.document_processor.index_book")
    @patch("app.services.document_processor.extract_book_metadata")
    @patch("app.services.document_processor._collect_known_authors")
    def test_analyze_book_pages_falls_back_from_toc_to_last_pages(
        self,
        mock_collect_known_authors: MagicMock,
        mock_extract_book_metadata: MagicMock,
        mock_index_book: MagicMock,
        mock_extract_works: MagicMock,
        mock_extract_pages: MagicMock,
    ) -> None:
        """The processor should retry on the last-page window after TOC failure."""

        mock_collect_known_authors.return_value = []
        mock_extract_book_metadata.return_value = BookMetadataResult(
            summary="summary",
            metadata=BookMetadata(book_title="Book", main_author="Author"),
        )
        mock_index_book.side_effect = [
            TOCSearchResult(
                works=[],
                toc=None,
                toc_find_failed=True,
                toc_failure_reason="No TOC in candidate set",
            ),
            TOCSearchResult(
                works=[WorkEntry(title="Work", start_page=10, end_page=12)],
                toc=TOCEntry(title="Мазмұны", start_page=9, end_page=9),
            ),
        ]
        mock_extract_works.return_value = [make_page(10, "Work body. " * 10)]
        mock_extract_pages.return_value = [make_page(10, "Page body. " * 10)]

        pages = [make_page(page, f"Body {page}") for page in range(1, 25)]
        db = MagicMock()

        analysis, work_docs, page_docs, final_file_name = (
            document_processor._analyze_book_pages(
                db=db,
                kb_id=1,
                task_id=2,
                file_name="book.json",
                pages=pages,
                display_suffix=".json",
            )
        )

        self.assertEqual("Author", analysis["metadata"]["main_author"])
        self.assertEqual(1, len(work_docs))
        self.assertEqual(1, len(page_docs))
        self.assertEqual("Author - Book.json", final_file_name)
        self.assertEqual(2, mock_index_book.call_count)
        metadata_input = mock_extract_book_metadata.call_args.args[0]
        first_input = mock_index_book.call_args_list[0].args[0]
        second_input = mock_index_book.call_args_list[1].args[0]
        self.assertIn("First pages:", metadata_input)
        self.assertIn("Last pages:", metadata_input)
        self.assertIn("Candidate TOC pages:", first_input)
        self.assertIn("Last 15 pages:", second_input)

    @patch("app.services.document_processor.index_book")
    @patch("app.services.document_processor.extract_book_metadata")
    @patch("app.services.document_processor._collect_known_authors")
    def test_analyze_book_pages_fails_after_all_three_toc_attempts(
        self,
        mock_collect_known_authors: MagicMock,
        mock_extract_book_metadata: MagicMock,
        mock_index_book: MagicMock,
    ) -> None:
        """The processor should fail only after all three TOC attempts."""

        mock_collect_known_authors.return_value = []
        mock_extract_book_metadata.return_value = BookMetadataResult(
            summary="summary",
            metadata=BookMetadata(book_title="Book", main_author="Author"),
        )
        mock_index_book.side_effect = [
            TOCSearchResult(
                works=[],
                toc=None,
                toc_find_failed=True,
                toc_failure_reason="Candidate TOC failed",
            ),
            TOCSearchResult(
                works=[],
                toc=None,
                toc_find_failed=True,
                toc_failure_reason="Last pages failed",
            ),
            TOCSearchResult(
                works=[],
                toc=None,
                toc_find_failed=True,
                toc_failure_reason="First pages failed",
            ),
        ]

        pages = [make_page(page, f"Body {page}") for page in range(1, 25)]

        with self.assertRaisesRegex(
            document_processor.BookIndexingError,
            "TOC find failed: First pages failed",
        ):
            document_processor._analyze_book_pages(
                db=MagicMock(),
                kb_id=1,
                task_id=2,
                file_name="book.json",
                pages=pages,
                display_suffix=".json",
            )

        self.assertEqual(3, mock_index_book.call_count)
        third_input = mock_index_book.call_args_list[2].args[0]
        self.assertIn("First 15 pages:", third_input)

    @patch("app.services.document_processor.extract_pages")
    @patch("app.services.document_processor.extract_works")
    @patch("app.services.document_processor.index_book")
    @patch("app.services.document_processor.extract_book_metadata")
    @patch("app.services.document_processor._collect_known_authors")
    def test_analyze_book_pages_applies_alihan_page_offset(
        self,
        mock_collect_known_authors: MagicMock,
        mock_extract_book_metadata: MagicMock,
        mock_index_book: MagicMock,
        mock_extract_works: MagicMock,
        mock_extract_pages: MagicMock,
    ) -> None:
        """Alihan Bokeihan uploads should shift TOC-derived work pages by 16."""

        mock_collect_known_authors.return_value = []
        mock_extract_book_metadata.return_value = BookMetadataResult(
            summary="summary",
            metadata=BookMetadata(
                book_title="Әлихан Бөкейхан шығармалары",
                main_author="Әлихан Бөкейхан",
            ),
        )
        mock_index_book.return_value = TOCSearchResult(
            works=[WorkEntry(title="Work", start_page=45, end_page=50)],
            toc=TOCEntry(title="Мазмұны", start_page=7, end_page=8),
        )
        mock_extract_works.return_value = [make_page(61, "Work body. " * 10)]
        mock_extract_pages.return_value = [make_page(61, "Page body. " * 10)]

        analysis, _, _, _ = document_processor._analyze_book_pages(
            db=MagicMock(),
            kb_id=1,
            task_id=2,
            file_name="ocr.json",
            pages=[make_page(page, f"Body {page}") for page in range(1, 80)],
            display_suffix=".json",
        )

        indexed_book = mock_extract_works.call_args.args[1]
        self.assertEqual(61, indexed_book.works[0].start_page)
        self.assertEqual(66, indexed_book.works[0].end_page)
        self.assertEqual(16, analysis["page_offset"])
        self.assertEqual(61, analysis["works"][0]["start_page"])
        self.assertEqual(66, analysis["works"][0]["end_page"])


if __name__ == "__main__":
    unittest.main()
