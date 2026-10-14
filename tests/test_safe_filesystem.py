from deepagents.backends import FilesystemBackend
from virtual_reactor_api.safe_filesystem import ResearchFilesystemBackend

def test_unicode_grep_falls_back_without_losing_evidence(tmp_path,monkeypatch):
    text='原研处方\n乳糖 50mg\n淀粉 20mg\n'
    (tmp_path/'evidence.txt').write_text(text,encoding='utf-8')
    def broken(*args,**kwargs):raise UnicodeDecodeError('gbk',b'\xff',0,1,'invalid')
    monkeypatch.setattr(FilesystemBackend,'_ripgrep_search',broken)
    result=ResearchFilesystemBackend(root_dir=tmp_path,virtual_mode=True).grep('乳糖',max_count=2)
    assert result.error is None and len(result.matches)==1
    assert '50mg' in result.matches[0]['text']
    assert (tmp_path/'evidence.txt').read_text(encoding='utf-8')==text

def test_normal_rg_result_kept(tmp_path,monkeypatch):
    monkeypatch.setattr(FilesystemBackend,'_ripgrep_search',lambda *a,**k:({},False))
    assert ResearchFilesystemBackend(root_dir=tmp_path,virtual_mode=True).grep('absent').matches==[]
