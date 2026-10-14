from virtual_reactor_api.directory_backfill import extract_rows,search_rows,summary,import_converted_table
from virtual_reactor_api.origin_registry import OriginRegistry
import hashlib
import pytest

HTML='<table><tr><td>序号</td><td>药品通用名称</td><td>规格</td></tr><tr><td>1-1</td><td>药品甲</td><td>5mg</td></tr></table>'
def test_no_guessed_columns():
    assert extract_rows('<table><tr><td>1-1</td><td>药品甲</td></tr></table>')==[]
    r=extract_rows(HTML.replace('<td>5mg</td>','<td colspan="2">5mg</td>'))[0]
    assert r['fields']=={} and r['status']=='column_alignment_pending'

def test_original_provenance_and_history(tmp_path):
    reg=OriginRegistry(tmp_path);raw=b'original';sha=hashlib.sha256(raw).hexdigest();(reg.folder/sha).write_bytes(raw)
    s={'url':'https://example.org/notice','title':'第一批','authority':'regulator_reprint'}
    a={'url':'https://example.org/file.doc','sha256':sha}
    import_converted_table(reg,s,a,HTML)
    import_converted_table(reg,s,a,HTML)
    assert summary(reg)['row_count']==1
    assert search_rows(reg,'')==[]
    r=search_rows(reg,'药品甲')[0]
    assert r['source_sha256']==sha and r['current_eligibility']=='not_reconciled'
    (reg.folder/sha).write_bytes(b'changed')
    with pytest.raises(ValueError):import_converted_table(reg,s,a,HTML)
