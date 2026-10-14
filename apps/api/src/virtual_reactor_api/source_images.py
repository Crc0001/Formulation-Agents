"""Discover source-linked raster tables and preserve OCR geometry, not guessed curves."""
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
import io
from contextlib import closing
import threading
import math
import statistics

def table_statistics(rows):
    """Audit explicit numeric replicate rows without correcting source values."""
    if not rows or len(rows)<2 or len(rows)>500 or not rows[0]:raise ValueError('需要2–500行数值重复数据')
    if any(len(r)!=len(rows[0]) for r in rows):raise ValueError('各行列数必须一致')
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for r in rows for x in r):raise ValueError('仅接受有限数值，缺失值不可填零')
    return {'n':len(rows),'mean':[statistics.mean(c) for c in zip(*rows)],'sample_sd':[statistics.stdev(c) for c in zip(*rows)],'warning':'仅复算输入行，不确认样品身份、独立重复或原表正确性；原值未裁剪。'}

class Images(HTMLParser):
    def __init__(self, base):
        super().__init__(); self.base=base; self.sections=[]; self.items=[]
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag in ('section','figure'): self.sections.append((tag,a.get('id','')))
        if tag!='img': return
        src=urljoin(self.base,a.get('src',''))
        if urlsplit(src).scheme not in ('http','https'): return
        if not urlsplit(src).path.lower().endswith(('.jpg','.jpeg','.png','.webp','.tif','.tiff')): return
        locator=next((x[1] for x in reversed(self.sections) if x[1]),'')
        if not locator and 'graphic' not in a.get('class',''): return
        self.items.append({'image_id':len(self.items)+1,'url':src,'locator':locator or 'inline graphic','alt':a.get('alt','')})
    def handle_endtag(self,tag):
        if tag in ('section','figure') and self.sections: self.sections.pop()

def image_manifest(data, url):
    if data.startswith(b'%PDF'):return []
    parser=Images(url);parser.feed(data.decode('utf-8',errors='replace'))
    return parser.items[:80]

def is_challenge(text):
    t=text.lower()
    return len(text)<3000 and any(x in t for x in ('checking your browser','verify you are human','just a moment','enable javascript and cookies'))

_engine=None
_lock=threading.Lock()
_pdf_lock=threading.RLock()

def _serialized_pdf(fn):
    # PDFium is not thread-safe, including calls on different documents.
    from functools import wraps
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with _pdf_lock:
            return fn(*args, **kwargs)
    return wrapped

@_serialized_pdf
def pdf_pages(data):
    import pypdfium2 as pdfium
    with closing(pdfium.PdfDocument(data)) as doc:
        return len(doc)

@_serialized_pdf
def render_pdf_page(data, page_number, scale=2.5):
    """Render one physical PDF page, numbered from one; no script execution."""
    import pypdfium2 as pdfium
    if isinstance(page_number,bool) or not isinstance(page_number,int):raise ValueError('PDF页码须为整数')
    with closing(pdfium.PdfDocument(data)) as doc:
        if not 1<=page_number<=len(doc):raise ValueError('PDF页码超出范围')
        page=doc[page_number-1]
        try:
            w,h=page.get_size()
            if not isinstance(scale,(int,float)) or not 1<=scale<=4:raise ValueError("PDF渲染倍率须在1–4之间")
            if w*h*scale*scale>16000000:raise ValueError('PDF页面超过1600万像素预算')
            bitmap=page.render(scale=scale)
            try:
                output=io.BytesIO();bitmap.to_pil().save(output,format='PNG');return output.getvalue()
            finally:bitmap.close()
        finally:page.close()

def image_ocr(data):
    from PIL import Image
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR
    image=Image.open(io.BytesIO(data))
    if image.width*image.height>16000000:raise ValueError('图片超过1600万像素预算')
    image.load(); original=list(image.size)
    image=image.convert('RGB')
    scale=min(3,1600/image.width)
    if scale>1:image=image.resize((round(image.width*scale),round(image.height*scale)))
    global _engine
    with _lock:
        if _engine is None:_engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=2)
        boxes,_=_engine(np.asarray(image))
    cells=[{'text':text,'score':round(float(score),4),'box':[[round(float(x),2),round(float(y),2)] for x,y in box]} for box,text,score in (boxes or [])]
    if not cells:raise ValueError('图片未识别出文字，保留图像待人工核对')
    # Keep columns separate; rows are spatial grouping, not scientific interpretation.
    rows=[]
    for cell in sorted(cells,key=lambda c:sum(p[1] for p in c['box'])/4):
        cy=sum(p[1] for p in cell['box'])/4
        height=max(p[1] for p in cell['box'])-min(p[1] for p in cell['box'])
        if rows and abs(rows[-1]['y']-cy)<max(5,height*.5):rows[-1]['cells'].append(cell)
        else:rows.append({'y':cy,'cells':[cell]})
    for row in rows:row['cells'].sort(key=lambda c:min(p[0] for p in c['box']))
    return {'engine':'rapidocr_onnxruntime-1.4.4','original_size':original,'ocr_size':list(image.size),'rows':rows,
        'text':'\n'.join(' | '.join(c['text'] for c in r['cells']) for r in rows),
        'low_confidence_cells':sum(c['score']<.85 for c in cells),'minimum_confidence':min(c['score'] for c in cells),'coordinate_space':'ocr_size pixels; map to original using original_size/ocr_size','verified':False,'warning':'OCR候选，不是已核验原表值；保留小数逗号、超过100%的数值，核对表头/行列/样品及正文。不从曲线图的刻度文字反推曲线点。'}
