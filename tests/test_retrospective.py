from pathlib import Path
from copy import deepcopy
import numpy as np
from virtual_reactor_api.retrospective import execute,load_case

ROOT=Path(__file__).resolve().parents[1]
def test_holdout_no_leakage_and_unstable_quadratic():
    data=load_case(ROOT);r=execute(data)
    changed=deepcopy(data);changed['rows'][1]['q_pct']=[10,20,30,40,50]
    other=execute(changed)
    for a,b in zip(r['models'],other['models']):
        assert a['predicted']==b['predicted']
        assert a['prediction_sha256']==b['prediction_sha256']
        assert 'F2' not in a['train_ids']
    assert r['models'][0]['usable']
    assert not r['models'][1]['usable']
    # Symmetric training design: linear prediction at the center equals training mean.
    mean=np.mean([row['q_pct'] for row in data['rows'] if row['id']!='F2'],axis=0)
    assert np.allclose(r['models'][0]['predicted'],mean)

def test_source_raw_values_preserved():
    d=load_case(ROOT);r=execute(d)
    assert r['dataset']['rows'][2]['q_pct'][2]==89.67
    assert len(r['models'][0]['folds'])==9
    assert abs(sum(d['rows'][0][key] for key in ['mcc_pct','starch_pct','lactose_pct'])-99.21)<1e-10

def test_api_recomputes_and_preserves_versions(tmp_path):
    import json
    from fastapi.testclient import TestClient
    from virtual_reactor_api.dual_main import create_app
    target=tmp_path/'reference/mecobalamin-validation-20260925'
    target.mkdir(parents=True)
    (target/'dataset.json').write_text(json.dumps(load_case(ROOT)),encoding='utf-8')
    with TestClient(create_app(tmp_path)) as c:
        data={'name':'测试案例','api':'甲钴胺','market':'中国','strength':'0.5mg','strength_basis':'标示量','dosage_form':'片剂'}
        pid=c.post('/api/projects',json=data).json()['id']
        a=c.post(f'/api/projects/{pid}/retrospective-checks',json={}).json()
        b=c.post(f'/api/projects/{pid}/retrospective-checks',json={}).json()
        assert a['id']!=b['id']
        assert a['models']==b['models']
        snap=c.get('/api/projects/'+pid).json()
        assert len(snap['retrospective_checks'])==2
        assert not snap['anchors'] and not snap['baselines']
        bad=c.post('/api/projects',json={**data,'api':'其它药'}).json()['id']
        assert c.post(f'/api/projects/{bad}/retrospective-checks',json={}).status_code==422

def test_calculation_is_readable_evidence_not_record_id(tmp_path):
    from virtual_reactor_api.retrospective import register_calculation
    from virtual_reactor_api.capsule_store import Store
    store=Store(tmp_path/'evidence.sqlite3')
    from virtual_reactor_api.capsule_models import ProjectInput
    store.create_project(ProjectInput(name='test',api='test',market='test',strength='test',strength_basis='test'),'project')
    record={'id':'calculation-record','models':[]}
    eid=register_calculation(store,'project',record)
    assert eid!='calculation-record'
    assert register_calculation(store,'project',record)==eid
    evidence=store.rows('evidence','project')
    assert len(evidence)==1 and evidence[0]['basis']=='hypothesis'
