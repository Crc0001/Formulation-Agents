"""Read directory OOXML and explicit decimal list definitions; no inferred row numbers."""
import io,zipfile,re,html
from xml.etree import ElementTree as E
from .directory_backfill import extract_rows
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
def val(e,tag,default=''):
    x=e.find(W+tag) if e is not None else None
    return x.get(W+'val',default) if x is not None else default
def extract_docx(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        doc=E.fromstring(z.read('word/document.xml'))
        numbering=E.fromstring(z.read('word/numbering.xml')) if 'word/numbering.xml' in z.namelist() else E.Element('empty')
    definitions={n.get(W+'abstractNumId'):n for n in numbering.findall(W+'abstractNum')}
    nums={n.get(W+'numId'):n for n in numbering.findall(W+'num')}
    counters={};labels={}
    for p in doc.iter(W+'p'):
        pr=p.find(W+'pPr/'+W+'numPr')
        if pr is None:continue
        nid=val(pr,'numId');level=val(pr,'ilvl','0');num=nums.get(nid)
        if num is None or level!='0':continue
        abstract=definitions.get(val(num,'abstractNumId'))
        if abstract is None:continue
        lvl=abstract.find(W+"lvl[@"+W+"ilvl='0']")
        override=num.find(W+"lvlOverride[@"+W+"ilvl='0']")
        if override is not None and override.find(W+'lvl') is not None:lvl=override.find(W+'lvl')
        if lvl is None or val(lvl,'numFmt')!='decimal':continue
        template=val(lvl,'lvlText').strip()
        if not re.fullmatch(r'\d+[-－—]%1',template):continue
        start=int(val(override,'startOverride',val(lvl,'start','1')))
        counters[nid]=counters.get(nid,start-1)+1
        labels[id(p)]=template.replace('%1',str(counters[nid]))
    parts=[];origins={}
    for ti,t in enumerate(doc.iter(W+'tbl'),1):
        parts.append('<table>')
        for ri,row in enumerate(t.findall(W+'tr'),1):
            parts.append('<tr>')
            for ci,cell in enumerate(row.findall(W+'tc')):
                text=' '.join(''.join(p.itertext()) for p in cell.findall(W+'p'))
                if ci==0:
                    labs=[labels[id(p)] for p in cell.findall(W+'p') if id(p) in labels]
                    if len(labs)==1 and not re.fullmatch(r'\s*\d+[-－—]\d+\s*',text):
                        origins[(ti,ri)]={'numbering_label':labs[0],'original_cell_text':text};text=labs[0]
                pr=cell.find(W+'tcPr');span=val(pr,'gridSpan','1')
                merged=pr is not None and pr.find(W+'vMerge') is not None
                parts.append('<td colspan="'+span+'"'+(' rowspan="2"' if merged else '')+'>'+html.escape(text)+'</td>')
            parts.append('</tr>')
        parts.append('</table>')
    rows=extract_rows(''.join(parts))
    for r in rows:
        if (r['table'],r['row']) in origins:r['numbering_provenance']=origins[(r['table'],r['row'])]
        r['extraction']='OOXML table and explicit decimal numbering; pending review'
    return rows,' '.join(doc.itertext())
