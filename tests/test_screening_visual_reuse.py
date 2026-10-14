import asyncio,json
from test_table_vision import Store,Model,reading
from test_focused_screening import progress
from virtual_reactor_api.table_vision import read_table
from virtual_reactor_api.focused_screening import audit_progress
from virtual_reactor_api.screening_summary import summary_payload

def test_visual_table_and_metric_all_audit_paths(tmp_path):
    s=Store(tmp_path)
    asyncio.run(read_table(s,'pid','r',tmp_path,'im','Table 3',Model([reading(),reading()])))
    table=s.es[-1];table['id']='s'
    p=progress(calculation_evidence_ids=['c'])
    p['reasoning_chain']['calculation_ids']=['c']
    for m in p['mechanism_comparisons']:m['calculation_ids']=['c']
    s.es.append(dict(id='c',basis='hypothesis',fields={'source_metric_json':'{}'}))
    assert not audit_progress(p,s.es)['issues']
    s.es[0]['fields']['sha256']='corrupted'
    assert any('原始对照' in x for x in audit_progress(p,s.es)['issues'])
    assert any('原始数据' in x for x in audit_progress(p,s.es)['issues'])

def test_summary_preserves_frozen_recipe_and_full_calculation():
    cid='11111111-1111-1111-1111-111111111111'
    sid='22222222-2222-2222-2222-222222222222'
    record=json.dumps({'source_id':sid,'points':[[5,30],[10,50]]})
    e=[dict(id=cid,run_id='r',basis='hypothesis',title='calc',fields={'source_curve_model_json':record}),dict(id=sid,basis='source',text='a'*7000,fields={}),dict(id='unrelated',text='b'*100000)]
    payload={'request':'【处方辅料筛选】\n冻结基准：{"id":"b"}\n变化方案：{"id":"v","amount":10}\n问题：HPC与NS\n02研究包：'+('x'*100000),'checkpoint':{'calculation_ids':[cid]},'sources':e}
    result=summary_payload(payload,e,'r')
    assert result['request']['变化方案']['amount']==10
    assert result['saved_calculations'][0]['records']['source_curve_model_json']==record
    assert [x['id'] for x in result['sources']]==[sid]
    assert result['sources'][0]['text_truncated']
    assert len(json.dumps(result))<15000
