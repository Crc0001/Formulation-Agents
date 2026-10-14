import pytest
from virtual_reactor_api.baseline_sources import baseline_sources

def test_original_and_linked_ocr_kept_without_promotion():
    sources={'p':{'basis':'source','access':'page_text','fields':{'sha256':'abc'}},'i':{'basis':'image_estimate','access':'imported','title':'表5','fields':{'source_evidence_id':'p','source_document_sha256':'abc'}}}
    ids,warnings=baseline_sources(['i'],sources)
    assert ids==['i','p'] and '待核验' in warnings[0]
    assert sources['i']['basis']=='image_estimate'
    assert baseline_sources(['p'],sources)==(['p'],[])
    for invalid in [dict(sources,i={**sources['i'],'fields':{'source_evidence_id':'other','source_document_sha256':'abc'}}),dict(sources,p={**sources['p'],'fields':{'sha256':'different'}}),dict(sources,i={'basis':'search_lead','access':'page_text'})]:
        with pytest.raises(ValueError):baseline_sources(['i'],invalid)
    with pytest.raises(ValueError):baseline_sources(['missing'],sources)

def test_real_project_citations_save_in_isolated_app(tmp_path):
    import json,urllib.request,sqlite3
    from fastapi.testclient import TestClient
    from virtual_reactor_api.dual_main import create_app
    with urllib.request.urlopen('http://127.0.0.1:2806/api/projects/db6a655f-75fa-4c7a-a4c9-fccbc62e3c40') as response:s=json.load(response)
    r=next(x['report'] for x in reversed(s['origin']['runs']) if x.get('report',{}).get('origin_recommendation'))
    f=next(x for x in r['formulations'] if x['title']==r['origin_recommendation']['formula_title'])
    with TestClient(create_app(tmp_path,runner=lambda *args:None)) as c:
        p=c.post('/api/projects',json={'name':'isolated save','api':'左氧氟沙星','market':'中国','strength':'500mg','strength_basis':'活性成分'}).json();pid=p['id']
        with sqlite3.connect(tmp_path/'data/origin.sqlite3') as db:
            for e in s['origin']['evidence']:
                e={**e,'project_id':pid}
                db.execute('INSERT INTO evidence VALUES(?,?,?)',(e['id'],pid,json.dumps(e)))
        ingredients=[dict(id=str(i),name=x['name'],role='api' if i==0 else 'shell' if '包衣' in x['name'] else 'excipient',amount_mg=x['amount_mg']) for i,x in enumerate(f['components'])]
        res=c.post('/api/projects/'+pid+'/baselines',json=dict(title=f['title'],ingredients=ingredients,source_ids=f['source_ids'],process=r['origin_recommendation']['process'],api_particle='待核',mass_basis=f['applicability'],rationale='隔离验证'))
        assert res.status_code==200,res.text
        saved=res.json();assert saved['evidence_warnings'] and '待核验' in saved['mass_basis']
        assert saved['ingredients'][0]['amount_mg']==512.5
        assert set(f['source_ids'])<=set(saved['source_ids'])
