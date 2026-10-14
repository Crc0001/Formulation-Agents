import json,shutil
from pathlib import Path
import pytest
from virtual_reactor_api.final_calibration import execute
ROOT=Path(__file__).resolve().parents[1]
def test_final_batch_holdout_not_used_for_calibration(tmp_path):
 for name in ['reference/lactose-native-starch-20260926','reference/mecobalamin-validation-20260925']:
  (tmp_path/name).mkdir(parents=True)
 for name in ['reference/lactose-native-starch-20260926/data.json','reference/lactose-native-starch-20260926/actual-final-batches.json','reference/mecobalamin-validation-20260925/dataset.json']:
  shutil.copyfile(ROOT/name,tmp_path/name)
 a=execute(tmp_path,{'id':'b'},{'id':'v'})
 path=tmp_path/'reference/lactose-native-starch-20260926/actual-final-batches.json'
 data=json.loads(path.read_text(encoding='utf-8'));data['water'][2]=[50]*5;path.write_text(json.dumps(data),encoding='utf-8')
 b=execute(tmp_path,{'id':'b'},{'id':'v'})
 assert a['after']==b['after'] and a['k_after']==b['k_after']
 assert a['holdout_rmse_after_pp']!=b['holdout_rmse_after_pp']
 assert a['holdout_rmse_after_pp']==pytest.approx(1.004564032)
 assert a['rate_range_engineering'][1]==10 and a['target_variant_prediction'] is None


def test_direction_is_time_specific_and_not_quantitative():
 from test_native_starch_pair import fixture
 base,variant=fixture()
 t=execute(ROOT,base,variant)['trend']
 assert t['direction']=='降低' and t['late_consistent']
 assert t['outside_domain'] and t['after_core_pct']==pytest.approx(18.8888889)
 assert t['magnitude_prediction'] is None
 assert all(c['delta_q_pp'][j]<0 for c in t['contrasts'] for j in (2,3,4))
 assert any(c['delta_q_pp'][j]>0 for c in t['contrasts'] for j in (0,1))
 variant['ingredients'][1]['amount_mg']=7
 variant['ingredients'][2]['amount_mg']=53.3
 assert execute(ROOT,base,variant)['trend']['direction']=='未评估'
