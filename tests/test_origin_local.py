import hashlib,json
from virtual_reactor_api.origin_registry import OriginRegistry
from virtual_reactor_api.directory_backfill import initialize
from virtual_reactor_api.origin_local import preload
from virtual_reactor_api.capsule_store import Store
from virtual_reactor_api.capsule_models import ProjectInput
from virtual_reactor_api.origin_stages import identity_sources

def test_local_original_binding_is_idempotent_and_exact(tmp_path):
    reg=OriginRegistry(tmp_path);initialize(reg)
    store=Store(tmp_path/'project.sqlite3')
    p=store.create_project(ProjectInput(name='test',api='药A片',market='中国',strength='1mg',strength_basis='原文'))
    raw=b'original';sha=hashlib.sha256(raw).hexdigest();(reg.folder/sha).write_bytes(raw)
    for i,name in enumerate(('药A片','药A片剂其它')):
        r=dict(source_sha256=sha,source_url='https://example.org/original',entry_number=f'109-{i+1}',cells=[f'109-{i+1}',name,'A','1mg','holder','',''],table=1,row=i+1)
        with reg.db() as c:c.execute('insert into directory_rows values(?,?,?,?)',(r['source_url'],sha,r['entry_number'],json.dumps(r,ensure_ascii=False)))
    a=preload(reg,store,p['id']);b=preload(reg,store,p['id'])
    assert a==b and len(store.rows('evidence',p['id']))==1
    assert a['directory_sources'][0]['entries']==['109-1']
    (reg.folder/sha).write_bytes(b'changed')
    assert not preload(reg,store,p['id'])['directory_sources']

def test_english_label_and_approval_not_discarded_by_title():
    evidence=[dict(id=str(i),title=t,basis='source',source_url=url,text=text,fields={},created_at='2026') for i,(t,url,text) in enumerate([
        ('REDEMPLO label','https://dailymed.nlm.nih.gov/label','Inactive ingredients: water. Manufactured by Company.'),
        ('Arrowhead宣布中国NMPA批准Redemplo','https://ir.arrowheadpharma.com/file','Approved January 7, 2026.'),
        ('目录索引','https://example.org/index','参比目录')])]
    cards=identity_sources(evidence)
    assert {x['id'] for x in cards}=={'0','1','2'}
    assert 'Inactive ingredients' in next(x for x in cards if x['id']=='0')['text']
