"""Batch-by-batch public directory intake; raw rows remain historical observations."""
import asyncio,hashlib,json,re,sqlite3
from html.parser import HTMLParser
from urllib.parse import urljoin,urlparse
from datetime import datetime,timezone
import httpx
from .origin_registry import OriginRegistry,Links

class Tables(HTMLParser):
    def __init__(self,text):
        super().__init__();self.tables=[];self.stack=[];self.row=None;self.cell=None;self.feed(text)
    def handle_starttag(self,t,a):
        if t=='table':self.stack.append([])
        if not self.stack:return
        if t=='tr':self.row=[]
        if t in ('td','th') and self.row is not None:self.cell=['',dict(a)]
        if t=='br' and self.cell is not None:self.cell[0]+=' '
    def handle_data(self,s):
        if self.cell is not None:self.cell[0]+=s
    def handle_endtag(self,t):
        if t in ('td','th') and self.cell is not None and self.row is not None:
            self.row.append(self.cell);self.cell=None
        if t=='tr' and self.stack and self.row is not None:self.stack[-1].append(self.row);self.row=None
        if t=='table' and self.stack:self.tables.append(self.stack.pop())

def extract_rows(html):
    found=[]
    for table_no,table in enumerate(Tables(html).tables,1):
        headers=None
        for row_no,row in enumerate(table,1):
            values=[re.sub(r'\s+',' ',c[0]).strip() for c in row]
            if '序号' in values and any(re.sub(r'\s+','',''.join(x)).startswith('药品通用名') for x in values):headers=values;continue
            if not headers or not values or not re.fullmatch(r'\d+\s*[-－—]\s*\d+',values[0]):continue
            ident=re.sub(r'\s+','',values[0]).replace('－','-').replace('—','-')
            valid=len(values)==len(headers) and all(c[1].get('rowspan','1')=='1' and c[1].get('colspan','1')=='1' for c in row)
            found.append({'batch':int(ident.split('-')[0]),'entry_number':ident,'table':table_no,'row':row_no,
                'headers':headers,'cells':values,'fields':dict(zip(headers,values)) if valid else {},
                'status':'parsed_pending_review' if valid else 'column_alignment_pending','current_eligibility':'not_reconciled'})
    return found

def initialize(reg):
    with reg.db() as c:c.executescript('CREATE TABLE IF NOT EXISTS batch_sources(url TEXT PRIMARY KEY,payload TEXT); CREATE TABLE IF NOT EXISTS directory_rows(url TEXT,sha TEXT,entry TEXT,payload TEXT,PRIMARY KEY(url,sha,entry));')

def summary(reg):
    initialize(reg)
    with reg.db() as c:
        sources=[json.loads(x[0]) for x in c.execute('select payload from batch_sources')]
        counts=[{'batch':b,'rows':n} for b,n in c.execute("select json_extract(payload,'$.batch'),count(distinct entry) from directory_rows group by json_extract(payload,'$.batch') order by 1")]
    return {'sources':sources,'batches':counts,'row_count':sum(x['rows'] for x in counts),'note':'原公告历史条目，尚未完成后续调出/更正核对；不是当前有效资格判定。'}

def search_rows(reg,q):
    initialize(reg)
    if not q.strip():return []
    with reg.db() as c:
        rows=[json.loads(x[0]) for x in c.execute('select payload from directory_rows where payload like ? limit 300',('%'+q.replace('%','').replace('_','')+'%',))]
    return rows

def import_converted_table(reg,source,attachment,html):
    """Store converted DOC rows with original attachment hash, never conversion as original."""
    raw=reg.folder/attachment['sha256']
    if hashlib.sha256(raw.read_bytes()).hexdigest()!=attachment['sha256']:raise ValueError('original_hash_mismatch')
    entries=extract_rows(html)
    initialize(reg)
    with reg.db() as c:
        for item in entries:
            item.update(source_url=attachment['url'],source_sha256=attachment['sha256'],source_title=source['title'],notice_url=source['url'],authority=source['authority'],extraction='LibreOffice DOC to HTML; unverified machine transcription')
            c.execute('insert or ignore into directory_rows values(?,?,?,?)',(attachment['url'],attachment['sha256'],item['entry_number'],json.dumps(item,ensure_ascii=False)))
        attachment['extracted_rows']=len(entries)
        attachment['status']='rows_extracted_pending_review'
        c.execute('insert or replace into batch_sources values(?,?)',(source['url'],json.dumps(source,ensure_ascii=False)))
    return entries

async def backfill(root,index_urls):
    reg=OriginRegistry(root);initialize(reg);sem=asyncio.Semaphore(3)
    def save(v):
        with reg.db() as c:c.execute('insert or replace into batch_sources values(?,?)',(v['url'],json.dumps(v,ensure_ascii=False)))
    async with httpx.AsyncClient(timeout=20,follow_redirects=True) as client:
        async def fetch(url):
            async with sem:
                r=await client.get(url);r.raise_for_status()
                if len(r.content)>20_000_000:raise ValueError('file_too_large')
                return r
        candidates={}
        for url in index_urls:
            try:
                r=await fetch(url)
                for a in Links(r.text).links:
                    title=(a['text'].strip() or a['title']).strip();link=urljoin(str(r.url),a['href'])
                    if '参比制剂目录' in title and '第' in title and urlparse(link).scheme in ('http','https'):
                        candidates[link]={'url':link,'title':title,'discovered_from':url,'status':'located'}
            except Exception as ex:save({'url':url,'title':'目录索引','status':'index_failed','error':type(ex).__name__})
        async def intake(v):
            url=v['url'];v['checked_at']=datetime.now(timezone.utc).isoformat()
            try:
                r=await fetch(url);sha=hashlib.sha256(r.content).hexdigest()
                host=urlparse(str(r.url)).hostname or '';authority='regulator_reprint' if host.endswith('.gov.cn') else 'third_party_reprint'
                kind='draft' if '征求意见' in v['title'] else authority+'_pending_review'
                reg.archive(url,v['title'],r.content,kind);v.update(sha256=sha,authority=authority,status='notice_archived')
                entries=[] if kind=='draft' else extract_rows(r.text)
                with reg.db() as c:
                    for item in entries:
                        item.update(source_url=url,source_sha256=sha,source_title=v['title'],authority=authority)
                        c.execute('insert or ignore into directory_rows values(?,?,?,?)',(url,sha,item['entry_number'],json.dumps(item,ensure_ascii=False)))
                v['row_count']=len(entries);v['batches']=sorted({e['batch'] for e in entries});v['attachments']=[]
                if entries:v['status']='rows_extracted_pending_review'
                for a in Links(r.text).links:
                    link=urljoin(str(r.url),a['href']);path=urlparse(link).path.lower()
                    if not path.endswith(('.doc','.docx','.xls','.xlsx','.pdf')):continue
                    if urlparse(link).scheme not in ('http','https'):continue
                    try:
                        file=await fetch(link)
                        if file.content.lstrip().lower().startswith((b'<!doctype html',b'<html')):raise ValueError('not_attachment')
                        reg.archive(link,v['title']+' · 附件',file.content,'attachment_pending_extraction')
                        v['attachments'].append({'url':link,'sha256':hashlib.sha256(file.content).hexdigest(),'status':'downloaded','extension':path.rsplit('.',1)[-1]})
                    except Exception as ex:v['attachments'].append({'url':link,'status':'failed','error':type(ex).__name__})
            except Exception as ex:v.update(status='failed',error=type(ex).__name__)
            save(v)
        await asyncio.gather(*(intake(v) for v in candidates.values()))
    return summary(reg)
