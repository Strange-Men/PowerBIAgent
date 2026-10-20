"""Localization Completeness Gate: resources and explicit display boundaries."""
from pathlib import Path
import ast
import json
import re
import subprocess
import sys
from string import Formatter

ROOT=Path(__file__).resolve().parents[1]


def load(path):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ValueError('duplicate_key:'+key)
            result[key]=value
        return result
    return json.loads(path.read_bytes().decode('utf-8',errors='strict'),object_pairs_hook=unique)


def compare(zh,en,*,frontend=False):
    errors=[]
    if zh.keys()!=en.keys(): errors.append('locale_key_set_mismatch')
    semantic={}
    for key in zh.keys() & en.keys():
        if not isinstance(zh[key],str) or not isinstance(en[key],str) or not zh[key] or not en[key]:
            errors.append('invalid_resource:'+key);continue
        parameters=lambda text:set(re.findall(r'{{\s*([\w]+)',text)) if frontend else {name for _,name,_,_ in Formatter().parse(text) if name is not None}
        if parameters(zh[key])!=parameters(en[key]):errors.append('placeholder_mismatch:'+key)
        identity=(zh[key],en[key])
        base=re.sub(r'_(one|other|zero|two|few|many)$','',key)
        if identity in semantic and semantic[identity]!=base:
            errors.append('duplicate_semantic_key:'+key)
        semantic[identity]=base
    return errors


def run_checks(root=ROOT):
    errors=[]
    frontend=root/'frontend/src/i18n/locales'
    if {p.name for p in frontend.iterdir() if p.is_dir()}!={'zh-CN','en-US'}:
        errors.append('product_locale_set_mismatch')
    if {p.stem for p in (frontend/'zh-CN').glob('*.json')}!={'common','auth','chat','sidebar','composer','reports','resources','errors'}:
        errors.append('required_namespaces_missing')
    for zh in sorted((frontend/'zh-CN').glob('*.json')):
        try:errors.extend(zh.name+':'+e for e in compare(load(zh),load(frontend/'en-US'/zh.name),frontend=True))
        except (ValueError,OSError) as exc:errors.append(str(exc))
    if {p.name for p in (frontend/'zh-CN').glob('*.json')}!={p.name for p in (frontend/'en-US').glob('*.json')}:
        errors.append('namespace_mismatch')
    try:errors.extend(compare(load(root/'backend/app/presentation/locales/zh-CN.json'),load(root/'backend/app/presentation/locales/en-US.json')))
    except (ValueError,OSError) as exc:errors.append(str(exc))
    boundaries={
        **{f'presentation/{name}':None for name in ['builder.py','formatter.py','query_scope.py','models.py']},
        'report/fixed.py':None,'report/executive.py':None,'report/presentation.py':None,
        'facts/verified.py':'FactBoundedAnswerBuilder',
    }
    for name,owner in boundaries.items():
        path=root/'backend/app'/name
        tree=ast.parse(path.read_text(encoding='utf-8'))
        parents={c:n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
        for node in ast.walk(tree):
            if not isinstance(node,ast.Constant) or not isinstance(node.value,str) or not re.search('[\u3400-\u9fff]',node.value):continue
            if isinstance(parents.get(node),ast.Expr):continue
            ancestry=[]
            parent=node
            while parent in parents:
                parent=parents[parent]; ancestry.append(parent)
            if owner and not any(isinstance(p,ast.ClassDef) and p.name==owner for p in ancestry):continue
            # Canonical ReportSpec validators retain their pre-existing exact
            # title/table contracts. Only render/projection code is localized.
            if any(isinstance(p,(ast.FunctionDef,ast.AsyncFunctionDef)) and p.name in {'_validate_spec','_validate_tables'} for p in ancestry):continue
            # Existing temporal lexical grammar is parser code, not display text.
            if node.value==r'(\d{4})[年/-](\d{1,2})(?:月|$)':continue
            errors.append(f'hardcoded_presentation:{name}:{node.lineno}')
    for path in (root/'backend/app/report/templates').glob('*.html'):
        # CSS, placeholders, technical attributes and canonical IDs are excluded.
        for text in re.findall(r'>([^<>]+)<',path.read_text(encoding='utf-8')):
            if re.search('[\u3400-\u9fff]',text):errors.append('hardcoded_report_template:'+path.name)
    return errors


def main():
    errors=run_checks()
    if errors:
        print('\n'.join(errors));return 1
    result=subprocess.run(['node',str(ROOT/'frontend/scripts/check-localization.cjs')],cwd=ROOT)
    if result.returncode:return result.returncode
    print('Localization Completeness Gate: PASS');return 0


if __name__=='__main__':sys.exit(main())
