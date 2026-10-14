from virtual_reactor_api.patent_reader import patent_pdf_url,patent_table_pages
from pathlib import Path

def test_pdf_discovery():
 assert patent_pdf_url('<meta content="https://example.org/a.pdf" name="citation_pdf_url">','https://example.org') == 'https://example.org/a.pdf'
 assert patent_pdf_url('<a href="javascript:a.pdf">x</a>','https://example.org') is None

def test_real_patent_missing_table_pages():
 data=Path('reference/mgst-check/CN109172539A.pdf').read_bytes()
 pages=patent_table_pages(data)
 assert all(p in pages for p in [6,7,8,10])
