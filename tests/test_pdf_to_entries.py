import os
import re

import pytest

from khoj.processor.content.pdf.pdf_to_entries import PdfToEntries


def test_extract_text_closes_tempfile_before_loader_and_cleans_up(monkeypatch):
    """Regression test for #1368.

    On Windows, a NamedTemporaryFile(delete=True) path cannot be reopened by
    the document loader while the writer handle is open. The extractor must
    close the handle before handing the path to the loader, and remove the
    temp file afterwards on every code path.
    """
    tracked = {}

    class FakeTempFile:
        def __init__(self):
            self.name = "khoj_test_temp.pdf"
            self.closed = False

        def write(self, data):
            pass

        def flush(self):
            pass

        def close(self):
            self.closed = True

    def fake_named_tempfile(*args, **kwargs):
        fake = FakeTempFile()
        tracked["tempfile"] = fake
        return fake

    class FakeLoader:
        def __init__(self, path):
            assert path == tracked["tempfile"].name
            tracked["loader_path"] = path

        def load(self):
            tracked["closed_when_loaded"] = tracked["tempfile"].closed
            return []

    unlinked_paths = []
    real_unlink = os.unlink

    def tracking_unlink(path, *args, **kwargs):
        unlinked_paths.append(path)
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr("khoj.processor.content.pdf.pdf_to_entries.tempfile.NamedTemporaryFile", fake_named_tempfile)
    monkeypatch.setattr("khoj.processor.content.pdf.pdf_to_entries.PyMuPDFLoader", FakeLoader)
    monkeypatch.setattr("khoj.processor.content.pdf.pdf_to_entries.os.unlink", tracking_unlink)

    entries = PdfToEntries.extract_text(b"fake pdf bytes")

    assert entries == []
    assert tracked["loader_path"] == "khoj_test_temp.pdf"
    # The handle must be closed before the loader opens the path
    assert tracked["closed_when_loaded"] is True
    # The temp file must be removed after extraction
    assert unlinked_paths == ["khoj_test_temp.pdf"]


def test_extract_text_cleans_up_tempfile_on_loader_error(monkeypatch):
    """The temp file must still be removed when the loader raises."""

    class FakeTempFile:
        def __init__(self):
            self.name = "khoj_test_temp.pdf"

        def write(self, data):
            pass

        def flush(self):
            pass

        def close(self):
            pass

    unlinked_paths = []
    real_unlink = os.unlink

    def tracking_unlink(path, *args, **kwargs):
        unlinked_paths.append(path)
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(
        "khoj.processor.content.pdf.pdf_to_entries.tempfile.NamedTemporaryFile", lambda *a, **k: FakeTempFile()
    )

    class RaisingLoader:
        def __init__(self, path):
            raise RuntimeError("boom")

    monkeypatch.setattr("khoj.processor.content.pdf.pdf_to_entries.PyMuPDFLoader", RaisingLoader)
    monkeypatch.setattr("khoj.processor.content.pdf.pdf_to_entries.os.unlink", tracking_unlink)

    entries = PdfToEntries.extract_text(b"fake pdf bytes")

    assert entries == []
    assert unlinked_paths == ["khoj_test_temp.pdf"]


def test_single_page_pdf_to_jsonl():
    "Convert single page PDF file to jsonl."
    # Act
    # Extract Entries from specified Pdf files
    # Read singlepage.pdf into memory as bytes
    with open("tests/data/pdf/singlepage.pdf", "rb") as f:
        pdf_bytes = f.read()

    data = {"tests/data/pdf/singlepage.pdf": pdf_bytes}
    entries = PdfToEntries.extract_pdf_entries(pdf_files=data)

    # Assert
    assert len(entries) == 2
    assert len(entries[1]) == 1


def test_multi_page_pdf_to_jsonl():
    "Convert multiple pages from single PDF file to jsonl."
    # Act
    # Extract Entries from specified Pdf files
    with open("tests/data/pdf/multipage.pdf", "rb") as f:
        pdf_bytes = f.read()

    data = {"tests/data/pdf/multipage.pdf": pdf_bytes}
    entries = PdfToEntries.extract_pdf_entries(pdf_files=data)

    # Assert
    assert len(entries) == 2
    assert len(entries[1]) == 6


@pytest.mark.skip(reason="Temporarily disabled OCR due to performance issues")
def test_ocr_page_pdf_to_jsonl():
    "Convert multiple pages from single PDF file to jsonl."
    # Arrange
    expected_str = "playing on a strip of marsh"
    expected_str_with_variable_spaces = re.compile(expected_str.replace(" ", r"\s*"), re.IGNORECASE)

    # Extract Entries from specified Pdf files
    with open("tests/data/pdf/ocr_samples.pdf", "rb") as f:
        pdf_bytes = f.read()
    data = {"tests/data/pdf/ocr_samples.pdf": pdf_bytes}

    # Act
    entries = PdfToEntries.extract_pdf_entries(pdf_files=data)
    raw_entry = entries[1][0].raw

    # Assert
    assert len(entries) == 2
    assert len(entries[1]) == 1
    assert re.search(expected_str_with_variable_spaces, raw_entry) is not None


# Helper Functions
def create_file(tmp_path, entry=None, filename="document.pdf"):
    pdf_file = tmp_path / filename
    pdf_file.touch()
    if entry:
        pdf_file.write_text(entry)
    return pdf_file
