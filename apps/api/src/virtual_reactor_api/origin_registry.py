"""Shared official-directory archive. Discovery is not regulatory verification."""
import asyncio,hashlib,json,sqlite3
from datetime import datetime,timezone
from urllib.parse import urljoin,urlparse
import httpx
from html.parser import HTMLParser
class Links(HTMLParser):
    def __init__(self,html):
        super().__init__();self.links=[];self.current=None;self.text=[];self.feed(html)
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            v=dict(attrs);self.current={'href':v.get('href',''),'title':v.get('title',''),'text':''}
    def handle_data(self,data):
        self.text.append(data)
        if self.current is not None:self.current['text']+=data
    def handle_endtag(self,tag):
        if tag=='a' and self.current is not None:self.links.append(self.current);self.current=None

INDEXES=('https://www.nmpa.gov.cn/xxgk/ggtg/ypggtg/ypqtggtg/index.html','https://www.cde.org.cn/')

def official(url):
    host=urlparse(url).hostname or ''
    return urlparse(url).scheme=='https' and (host=='nmpa.gov.cn' or host.endswith('.nmpa.gov.cn') or host=='cde.org.cn' or host.endswith('.cde.org.cn'))

def discover(html,base):
    soup=Links(html);out=[]
    for a in soup.links:
        title=a['text'].strip() or a.get('title','');url=urljoin(base,a['href'])
        if official(url) and '参比制剂' in title and any(x in title for x in ('目录','调整','调出','更正')):
            out.append({'title':title,'url':url,'status':'draft' if '征求意见' in title else 'notice_pending_review'})
    return list({x['url']:x for x in out}.values())

class OriginRegistry:
    def __init__(self,root):
        self.folder=root/'data/origin-registry';self.folder.mkdir(parents=True,exist_ok=True)
        self.path=self.folder/'registry.sqlite3';self.lock=asyncio.Lock()
        with self.db() as c:c.executescript('CREATE TABLE IF NOT EXISTS documents(url TEXT,sha TEXT,payload TEXT,PRIMARY KEY(url,sha)); CREATE TABLE IF NOT EXISTS checks(id INTEGER PRIMARY KEY,payload TEXT);')
        old=root/'data/origin.sqlite3'
        if old.exists():
            with sqlite3.connect(old) as c:
                sources=[json.loads(r[0]) for r in c.execute('select payload from evidence')]
            for e in sources:
                url=e.get('source_url') or '';host=urlparse(url).hostname or ''
                if e.get('basis')!='source' or '目录' not in e.get('title','') or not (official(url) or host in ('mpa.shaanxi.gov.cn','amr.hainan.gov.cn')):continue
                f=e.get('fields',{});sha=f.get('original_sha256') or f.get('sha256')
                path=(root/f['original_file']).resolve() if f.get('original_file') else root/'data/documents'/str(sha)
                if path.is_relative_to(root.resolve()) and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==sha:
                    self.archive(url,e['title'],path.read_bytes(),'regulator_reprint_pending_review')
    def db(self):return sqlite3.connect(self.path)
    def status(self):
        with self.db() as c:
            checks=[json.loads(r[0]) for r in c.execute('select payload from checks order by id desc limit 10')]
            docs=[json.loads(r[0]) for r in c.execute('select payload from documents order by rowid desc')]
        return {'latest':checks[0] if checks else None,'documents':docs,'running':self.lock.locked(),
            'coverage':'尚未完成历批全量目录及逐条品种建库；当前为官方公告发现与原件归档。不能据此确认完整现行目录。'}
    def archive(self,url,title,data,kind):
        sha=hashlib.sha256(data).hexdigest();(self.folder/sha).write_bytes(data)
        v={'url':url,'title':title,'sha256':sha,'status':kind,'archived_at':datetime.now(timezone.utc).isoformat()}
        with self.db() as c:c.execute('insert or ignore into documents values(?,?,?)',(url,sha,json.dumps(v,ensure_ascii=False)))
    async def check(self,force=False):
        if self.lock.locked():return self.status()
        latest=self.status()['latest']
        if latest and not force and (datetime.now(timezone.utc)-datetime.fromisoformat(latest['checked_at'])).total_seconds()<21600:return self.status()
        async with self.lock:
            result={'checked_at':datetime.now(timezone.utc).isoformat(),'status':'partial','sources':[],'found':0}
            async with httpx.AsyncClient(timeout=12,follow_redirects=True) as client:
                for url in INDEXES:
                    try:
                        r=await client.get(url);r.raise_for_status()
                        if not official(str(r.url)):raise ValueError('unexpected_redirect')
                        html=r.text;items=discover(html,str(r.url))
                        if not items:raise ValueError('index_has_no_readable_directory_links')
                        self.archive(url,'官方目录入口快照',r.content,'index_snapshot')
                        result['sources'].append({'url':url,'status':'readable','links':len(items)})
                        for item in items[:20]:
                            try:
                                doc=await client.get(item['url']);doc.raise_for_status()
                                if not official(str(doc.url)):raise ValueError('unexpected_redirect')
                                if '参比制剂' not in doc.text or len(''.join(Links(doc.text).text))<150:raise ValueError('unreadable_notice')
                                self.archive(item['url'],item['title'],doc.content,item['status']);result['found']+=1
                                for a in Links(doc.text).links:
                                    link=urljoin(str(doc.url),a['href'])
                                    if official(link) and urlparse(link).path.lower().endswith(('.pdf','.doc','.docx','.xls','.xlsx')):
                                        attachment=await client.get(link);attachment.raise_for_status()
                                        if not official(str(attachment.url)) or attachment.headers.get('content-type','').startswith('text/html'):raise ValueError('attachment_not_original')
                                        self.archive(link,item['title']+' · '+a['text'].strip(),attachment.content,'attachment_pending_extraction')
                            except Exception as ex:result['sources'].append({'url':item['url'],'status':'failed','reason':type(ex).__name__})
                    except Exception as ex:result['sources'].append({'url':url,'status':'failed','reason':type(ex).__name__,'http_status':ex.response.status_code if isinstance(ex,httpx.HTTPStatusError) else None})
            result['status']='partial' if result['found'] else 'failed'
            with self.db() as c:c.execute('insert into checks(payload) values(?)',(json.dumps(result,ensure_ascii=False),))
        return self.status()
