"""Export four sibling skills and verify the extracted standard-library calculator."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

NAMES=('excipient-performance','excipient-grade-evidence','excipient-mechanism-model','excipient-model-validation')
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists():parser.error('Choose a new output path; existing package is preserved')
    root=Path(__file__).resolve().parents[2]
    entries={}
    for name in NAMES:
        folder=root/name
        if not (folder/'SKILL.md').is_file():raise ValueError(f'Missing sibling skill: {name}')
        for path in folder.rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix in ('.md','.py','.json','.yaml','.yml'):
                entries[path.relative_to(root).as_posix()]=path.read_bytes()
    manifest={'package_version':'1.0','entrypoint':'excipient-performance/SKILL.md',
        'minimum_runtime':'Python 3 standard library for powder_yield only; other calculators declare their own dependencies',
        'files':{name:hashlib.sha256(content).hexdigest() for name,content in entries.items()}}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.output,'x',zipfile.ZIP_DEFLATED) as package:
        for name,content in entries.items():package.writestr(name,content)
        package.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        package.writestr('START.md','# 辅料研究技能包\n\n先让模型读取 excipient-performance/SKILL.md。四个技能目录保持并列；无需原项目数据库或历史对话。具体交接与启动提示见 excipient-performance/references/portable-workflow.md。\n\n离线计算验收：\n\n```sh\npython excipient-mechanism-model/scripts/check_powder_yield.py\npython excipient-mechanism-model/scripts/powder_yield.py --input excipient-mechanism-model/assets/powder-yield-example.json --output result.json\n```\n\n检索需要宿主提供联网工具；本包不含密钥、用户处方、项目数据库或文献PDF。运行示例不证明目标制剂预测有效。\n')
    with tempfile.TemporaryDirectory(prefix='excipient-portable-check-') as temporary:
        dest=Path(temporary)
        with zipfile.ZipFile(args.output) as package:package.extractall(dest)
        for name,digest in manifest['files'].items():
            assert hashlib.sha256((dest/name).read_bytes()).hexdigest()==digest
        check=subprocess.run([sys.executable,'-I',str(dest/'excipient-mechanism-model/scripts/powder_yield.py'),
            '--input',str(dest/'excipient-mechanism-model/assets/powder-yield-example.json'),'--output',str(dest/'result.json')],
            cwd=dest,capture_output=True,text=True,check=True)
        result=json.loads((dest/'result.json').read_text(encoding='utf-8'))
        assert abs(result['tau_kPa']['unsieved'][1]-.37312655972007125)<1e-12
        assert abs(result['tau_kPa']['sieved'][1]-.5211289006642442)<1e-12
        assert result['target_dissolution_prediction'] is None
    receipt={'package':str(args.output),'sha256':hashlib.sha256(args.output.read_bytes()).hexdigest(),
      'file_count':len(entries),'extracted_isolated_python_run':'passed','historical_conversation_required':False,
      'other_model_behavior_evaluated':False}
    args.output.with_suffix('.verification.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=True))

if __name__=='__main__':main()
