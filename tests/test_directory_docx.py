import io
import zipfile
from virtual_reactor_api.directory_docx import extract_docx

def document(template=' 78-%1', override='', numbered=True):
    ns='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    def cell(text, number=False):
        pr='<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="9"/></w:numPr></w:pPr>' if number else ''
        return f'<w:tc><w:p>{pr}<w:r><w:t>{text}</w:t></w:r></w:p></w:tc>'
    table='<w:tr>'+cell('序号')+cell('药 品通用名')+'</w:tr>'
    for name in ('药甲','药乙'):
        table+='<w:tr>'+cell('',numbered)+cell(name)+'</w:tr>'
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('word/document.xml',f'<w:document xmlns:w="{ns}"><w:body><w:tbl>{table}</w:tbl></w:body></w:document>')
        z.writestr('word/numbering.xml',f'<w:numbering xmlns:w="{ns}"><w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="{template}"/></w:lvl></w:abstractNum><w:num w:numId="9"><w:abstractNumId w:val="1"/>{override}</w:num></w:numbering>')
    return out.getvalue()

def test_explicit_numbering_and_whitespace_header():
    rows,_=extract_docx(document())
    assert [r['entry_number'] for r in rows]==['78-1','78-2']
    assert rows[0]['numbering_provenance']['original_cell_text']==''
    assert rows[1]['cells'][1]=='药乙'

def test_override_start_and_no_guessed_batch():
    rows,_=extract_docx(document(override='<w:lvlOverride w:ilvl="0"><w:startOverride w:val="4"/></w:lvlOverride>'))
    assert [r['entry_number'] for r in rows]==['78-4','78-5']
    assert extract_docx(document(template='%1'))[0]==[]
    assert extract_docx(document(numbered=False))[0]==[]
