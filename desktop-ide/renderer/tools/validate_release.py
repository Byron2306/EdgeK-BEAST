#!/usr/bin/env python3
from __future__ import annotations
import json, pathlib, re, subprocess, sys
from html.parser import HTMLParser

root=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else pathlib.Path(__file__).resolve().parents[1]).resolve()
VERSION='3.1.0-rc4'; BUILD='BEAST-IDE-3.1.0-RC4'

class Parser(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids=[]; self.refs=[]; self.scripts=[]; self.styles=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if a.get('id'): self.ids.append(a['id'])
        for key in ('src','href'):
            value=a.get(key,'')
            if value and not value.startswith(('http:','https:','data:','#','mailto:')):
                self.refs.append(value.split('?',1)[0])
        if tag=='script' and a.get('src'): self.scripts.append(a['src'])
        if tag=='link' and 'stylesheet' in (a.get('rel') or ''): self.styles.append(a.get('href',''))

html=(root/'index.html').read_text(encoding='utf-8')
p=Parser(); p.feed(html)
duplicates=sorted({item for item in p.ids if p.ids.count(item)>1})
missing=[]
for ref in p.refs:
    if ref.startswith('../node_modules/'): continue
    target=(root/ref).resolve()
    if not target.exists(): missing.append(ref)

js_fail=[]
for file in sorted((root/'js').rglob('*.js')):
    result=subprocess.run(['node','--check',str(file)],capture_output=True,text=True)
    if result.returncode:
        js_fail.append({'file':str(file.relative_to(root)),'error':result.stderr[-1600:]})

css_path=root/'css/beast-production.css'; css=css_path.read_text(encoding='utf-8')
css_balance={'braces':css.count('{')-css.count('}'),'comments':css.count('/*')-css.count('*/')}
css_missing=[]
for raw in re.findall(r'url\(([^)]+)\)',css):
    value=raw.strip().strip('"\'')
    if not value or value.startswith(('data:','http:','https:','#')): continue
    target=(css_path.parent/value).resolve()
    if not target.exists(): css_missing.append(value)

manifest=json.loads((root/'assets/manifest.json').read_text())
release_manifest=json.loads((root/'RELEASE_MANIFEST.json').read_text())
summary=json.loads((root/'acceptance/RC4_VISUAL_ACCEPTANCE_SUMMARY.json').read_text())
probe=json.loads((root/'acceptance/RC4_ANIMATION_TEMPORAL_PROBE.json').read_text())
metric_files=sorted((root/'acceptance').glob('RC4_VISUAL_METRICS_*.json'))
scenario_count=0; metric_failures=[]
for file in metric_files:
    data=json.loads(file.read_text())
    results=data.get('results',[]); scenario_count+=len(results)
    for item in results:
        checks={
          'root':item.get('rootCount')==1,
          'ids':not item.get('duplicateIds'),
          'header':not (item.get('head') and item['head'].get('overlap')),
          'overflow':item.get('body',{}).get('w',0)<=item.get('body',{}).get('cw',0)+1,
          'boot':not item.get('bootError'),'runtime':not item.get('errors'),
          'visual':bool(item.get('visual',{}).get('running')),
          'text':not item.get('smallText')
        }
        if not all(checks.values()): metric_failures.append({'file':file.name,'route':item.get('route'),'checks':checks})

old_owner_files=['js/beast-atmosphere.js','js/beast-production-visual.js','js/beast-phase10-app.js','js/beast-phase11-app.js']
old_owner_files_present=[x for x in old_owner_files if (root/x).exists()]
active_identity_files=['index.html','assets/manifest.json','RELEASE_MANIFEST.json','acceptance/release-runner.html','acceptance/release-runner.js','js/beast-release-app.js','js/beast-release-guard.js','js/beast-visual-runtime.js']
stale_identity=[]
for rel in active_identity_files:
    text=(root/rel).read_text(errors='ignore')
    if re.search(r'3\.1\.0-rc3|BEAST-IDE-3\.1\.0-RC3|BEAST IDE RC3',text,re.I): stale_identity.append(rel)

named_corporate_fonts=sorted(set(re.findall(r'(?i)\b(?:Arial(?:\s+Narrow|\s+Black)?|Times New Roman|Times|Georgia|Segoe UI|Helvetica)\b',css)))
hacker_fonts=['Orbitron','Oxanium','Chakra Petch','Aldrich','Rajdhani','Share Tech Mono','JetBrains Mono','IBM Plex Mono','Azeret Mono','Space Mono']
missing_hacker_fonts=[name for name in hacker_fonts if name not in css and name not in html]
font_files=[str(x.relative_to(root)) for x in root.rglob('*') if x.suffix.lower() in {'.ttf','.otf','.woff','.woff2'}]
local_styles=[x for x in p.styles if not x.startswith(('http:','https:'))]

checks={
 'version':manifest.get('version'),'release_id':manifest.get('release_id'),'build':release_manifest.get('build_id'),
 'duplicate_ids':duplicates,'missing_html_references':sorted(set(missing)),'missing_css_assets':sorted(set(css_missing)),
 'javascript_files_checked':len(list((root/'js').rglob('*.js'))),'javascript_syntax_failures':js_fail,'css_balance':css_balance,
 'page_outlets':html.count('id="beastPageOutlet"'),'context_rails':html.count('id="beastContextRail"'),
 'application_owners':p.scripts.count('js/beast-release-app.js'),'visual_runtime_owners':p.scripts.count('js/beast-visual-runtime.js'),
 'accessibility_owners':p.scripts.count('js/beast-accessibility-performance.js'),'release_guard_owners':p.scripts.count('js/beast-release-guard.js'),
 'local_production_stylesheets':local_styles,'old_owner_files_present':old_owner_files_present,'stale_active_release_identity':stale_identity,
 'named_corporate_fonts':named_corporate_fonts,'missing_requested_hacker_fonts':missing_hacker_fonts,'font_files_bundled':font_files,
 'visual_metric_profiles':len(metric_files),'visual_metric_scenarios':scenario_count,'visual_metric_failures':metric_failures,
 'visual_acceptance_status':summary.get('status'),'unexpected_clipping_candidates':summary.get('unexpected_clipping_candidates',[]),
 'intentional_overflow_candidates':len(summary.get('intentional_overflow_candidates',[])),
 'animation_temporal_changed_percent':probe.get('changed_percent',0),
 'animation_runtime_running':bool(probe.get('runtime_state',{}).get('visual',{}).get('running')),
 'animation_layers':{k:probe.get('runtime_state',{}).get(k) for k in ('matrix','front','grid','cards')},
}
required=(manifest.get('version')==VERSION and manifest.get('release_id')==BUILD and release_manifest.get('version')==VERSION and release_manifest.get('build_id')==BUILD)
pass_condition=(required and not duplicates and not missing and not css_missing and not js_fail and not any(css_balance.values()) and checks['page_outlets']==1 and checks['context_rails']==1 and checks['application_owners']==1 and checks['visual_runtime_owners']==1 and checks['accessibility_owners']==1 and checks['release_guard_owners']==1 and local_styles==['css/beast-production.css'] and not old_owner_files_present and not stale_identity and not named_corporate_fonts and not missing_hacker_fonts and not font_files and len(metric_files)==5 and scenario_count==110 and not metric_failures and summary.get('status')=='PASS' and not summary.get('unexpected_clipping_candidates') and probe.get('changed_percent',0)>0.5 and probe.get('runtime_state',{}).get('visual',{}).get('running') and probe.get('runtime_state',{}).get('matrix') and probe.get('runtime_state',{}).get('front') and probe.get('runtime_state',{}).get('grid'))
checks['status']='PASS' if pass_condition else 'FAIL'
output=json.dumps(checks,indent=2,ensure_ascii=False)+"\n"
(root/'RELEASE_VALIDATION.json').write_text(output,encoding='utf-8')
print(output,end='')
if not pass_condition: sys.exit(1)
