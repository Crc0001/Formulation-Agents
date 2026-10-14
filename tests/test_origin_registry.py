import asyncio
from virtual_reactor_api.origin_registry import OriginRegistry,discover,official

def test_discovery_distinguishes_draft_and_rejects_offsite():
    html='<a href="/a">参比制剂目录（征求意见稿）</a><a href="/b">参比制剂调出目录</a><a href="https://evil.test/a">参比制剂目录</a>'
    rows=discover(html,'https://www.cde.org.cn/')
    assert len(rows)==2 and rows[0]['status']=='draft'
    assert rows[1]['status']=='notice_pending_review'
    assert not official('https://www.nmpa.gov.cn.evil.test/a')

def test_archive_retains_versions_and_no_false_completeness(tmp_path):
    r=OriginRegistry(tmp_path)
    r.archive('https://www.cde.org.cn/a','a',b'one','draft')
    r.archive('https://www.cde.org.cn/a','a',b'one','draft')
    r.archive('https://www.cde.org.cn/a','a',b'two','draft')
    assert len(r.status()['documents'])==2
    assert r.status()['latest'] is None
    assert '尚未完成' in r.status()['coverage']

def test_failed_check_not_no_updates(tmp_path,monkeypatch):
    import httpx
    async def fail(*a,**kw):raise httpx.ConnectError('offline')
    monkeypatch.setattr(httpx.AsyncClient,'get',fail)
    r=OriginRegistry(tmp_path);s=asyncio.run(r.check())
    assert s['latest']['status']=='failed' and s['latest']['found']==0
    assert asyncio.run(r.check())['latest']==s['latest']

def test_autostart_existing_archive_does_not_restart(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from virtual_reactor_api.dual_main import create_app
    async def check(self,force=False):return self.status()
    monkeypatch.setattr(OriginRegistry,'check',check)
    async def runner(store,rid,root):store.finish(rid,'partial',report={'summary':'未取得身份','findings':[],'gaps':['身份待查']})
    with TestClient(create_app(tmp_path,runner=runner)) as c:
        p=c.post('/api/projects',json={'name':'new','api':'test','market':'中国','strength':'500mg','strength_basis':'活性成分'}).json()['id']
        r=c.post(f'/api/projects/{p}/origin-autostart');assert r.status_code==200
        import time
        for _ in range(50):
            rows=c.get(f'/api/projects/{p}').json()['origin']['runs']
            if rows and rows[-1]['status'] not in ('queued','running'):break
            time.sleep(.02)
        assert len(rows)==1
        assert c.post(f'/api/projects/{p}/origin-autostart').json()['status'] in ('existing_archive','running')
        assert len(c.get(f'/api/projects/{p}').json()['origin']['runs'])==1
