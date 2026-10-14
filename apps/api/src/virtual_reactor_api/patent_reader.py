"""Restricted Google Patents reader with example-level provenance."""
from __future__ import annotations

import html
import json
import re

import httpx
from langchain_core.tools import BaseTool, ToolException, tool

from virtual_reactor_api.evaluation_recorder import record_evaluation_event
from virtual_reactor_api.patent_evidence import extract_patent_examples


_PUBLICATION = re.compile(r"^[A-Z]{2}[0-9]+[A-Z][0-9]?$", re.I)


def create_google_patent_reader_tool(
    api_key: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> BaseTool:
    @tool("read_google_patent_examples")
    async def read_google_patent_examples(publication_number: str) -> str:
        """Read one Google Patents document and extract numbered examples with exact provenance."""
        normalized = publication_number.strip().upper()
        if not _PUBLICATION.fullmatch(normalized):
            raise ToolException("专利公开号格式无效，例如 CN102491902A。")
        source_url = f"https://patents.google.com/patent/{normalized}/en"
        record_evaluation_event(
            "patent_document_request",
            {"publicationNumber": normalized, "sourceUrl": source_url},
        )
        try:
            async with httpx.AsyncClient(
                transport=transport, timeout=20, follow_redirects=True
            ) as client:
                response = await client.get(
                    "https://serpapi.com/search",
                    params={
                        "engine": "google_patents_details",
                        "patent_id": f"patent/{normalized}/en",
                        "output": "html",
                        "api_key": api_key,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise ToolException(f"SerpApi 专利全文读取失败：{error.__class__.__name__}") from error
        text = _html_to_text(response.text)
        examples = extract_patent_examples(
            text, patent_number=normalized, source_url=source_url
        )
        result = {
            "publicationNumber": normalized,
            "sourceUrl": source_url,
            "accessLevel": "example_text" if examples else "full_text",
            "examples": examples,
            "warning": None if examples else "全文中未识别到编号实施例，不得声称实施例条件。",
            "text": text[:45000],
            "textTruncated": len(text) > 45000,
            "pdfUrl": patent_pdf_url(response.text, source_url),
        }
        record_evaluation_event(
            "patent_document_result",
            {
                "publicationNumber": normalized,
                "sourceUrl": source_url,
                "provider": "serpapi:google_patents_details",
                "exampleCount": len(examples),
            },
        )
        return json.dumps(result, ensure_ascii=False)

    read_google_patent_examples.handle_tool_error = lambda error: str(error)
    return read_google_patent_examples


def _html_to_text(value: str) -> str:
    value = re.sub(r"(?is)<(?:script|style).*?>.*?</(?:script|style)>", " ", value)
    value = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</section>|</tr>|</li>|</h[1-6]>", "\n", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\n\s*\n+", "\n", value)
    return value.strip()


def patent_pdf_url(markup: str, base: str) -> str | None:
    """Keep original PDF link before HTML stripping loses image tables."""
    from html.parser import HTMLParser
    from urllib.parse import urljoin, urlsplit
    class Links(HTMLParser):
        found = None
        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            candidate = a.get('content') if tag == 'meta' and a.get('name') == 'citation_pdf_url' else a.get('href') if tag == 'a' else None
            if candidate:
                url = urljoin(base, candidate)
                if urlsplit(url).scheme == 'https' and urlsplit(url).path.lower().endswith('.pdf'):
                    self.found = self.found or url
    parser = Links(); parser.feed(markup)
    return parser.found


def prioritized_patent_table_pages(data: bytes) -> list[int]:
    """Read actual example/composition pages before cover pages; retain all candidates."""
    import io
    from pypdf import PdfReader
    reader=PdfReader(io.BytesIO(data))
    scored=[]
    for i,page in enumerate(reader.pages):
        text=page.extract_text() or ''
        example=bool(re.search(r'实施例|对照例|对比例|\bexample\b',text,re.I))
        composition=bool(re.search(r'处方|质量百分|成分|composition|formulation',text,re.I))
        if composition or re.search(r'表\s*\d+|\btable\s*\d+',text,re.I) or not text.strip():
            score=4*example+3*composition+int(not text.strip())
            scored.append((-score,i+1))
    return [page for _,page in sorted(scored)]

def patent_table_pages(data: bytes) -> list[int]:
    """Locate candidate formula/table pages, including image-only scans. No numeric inference."""
    import io
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    candidates = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ''
        if re.search(r'表\s*\d+|\btable\s*\d+|处方|composition|formulation', text, re.I) or not text.strip():
            candidates.append(i + 1)
    return candidates
