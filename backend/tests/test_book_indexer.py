import unittest

from langchain_core.documents import Document as LangchainDocument

from app.services.book_indexer import (
    BookIndex,
    BookMetadata,
    WorkEntry,
    build_analysis_input,
    extract_pages,
    extract_works,
)


def make_page(page_number: int, text: str) -> LangchainDocument:
    """Build a minimal OCR page document for tests."""

    return LangchainDocument(page_content=text, metadata={"page": page_number})


class BookIndexerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
