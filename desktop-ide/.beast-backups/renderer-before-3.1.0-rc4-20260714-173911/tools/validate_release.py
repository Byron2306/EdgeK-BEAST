#!/usr/bin/env python3
from pathlib import Path
from html.parser import HTMLParser
import subprocess, json, re, sys, hashlib

root=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
class P(HTMLParser):
    def __init__(self): super().__init__(); self.ids=[]; self.refs=[]; self.scripts=[]; self.styles=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        for key in ('src','href'):
            v=a.get(key,'')
            if v and not re.match(r'^(https?:|data:|#|mailto:)',v):self.refs.append(v.split('?',1)[0])
        if tag=='script' and a.get('src'):self.scripts.append(a['src'])
        if tag=='link' and a.get('rel')=='stylesheet':self.styles.append(a.get('href',''))
html=(root/'index.html').read_text(encoding='utf-8'); p=P(); p.feed(html)
missing=[]
for ref in p.refs:
    target=(root/ref).resolve()
    if ref.startswith('../node_modules/'): continue
    if not target.exists():missing.append(ref)
dupes=sorted({x for x in p.ids if p.ids.count(x)>1})
js_fail=[]
for f in sorted((root/'js').rglob('*.js')):
    r=subprocess.run(['node','--check',str(f)],capture_output=True,text=True)
    if r.returncode:js_fail.append({'file':str(f.relative_to(root)),'error':r.stderr[-1000:]})
css=(root/'css/beast-production.css').read_text(encoding='utf-8')
css_balance={'braces':css.count('{')-css.count('}'),'comments':css.count('/*')-css.count('*/')}
manifest=json.loads((root/'assets/manifest.json').read_text())
checks={
 'version':manifest.get('version'),'release_id':manifest.get('release_id'),'duplicate_ids':dupes,'missing_references':sorted(set(missing)),
 'javascript_syntax_failures':js_fail,'css_balance':css_balance,'page_outlets':html.count('id="beastPageOutlet"'),
 'context_rails':html.count('id="beastContextRail"'),'release_apps':p.scripts.count('js/beast-release-app.js'),
 'release_guards':p.scripts.count('js/beast-release-guard.js'),'accessibility_owners':p.scripts.count('js/beast-accessibility-performance.js'),
 'legacy_phase_apps':[s for s in p.scripts if re.search(r'beast-phase(?:10|11)-app',s)],
 'font_files_bundled':[str(x.relative_to(root)) for x in root.rglob('*') if x.suffix.lower() in {'.ttf','.otf','.woff','.woff2'}]
}
checks['status']='PASS' if not dupes and not missing and not js_fail and not any(css_balance.values()) and checks['page_outlets']==1 and checks['context_rails']==1 and checks['release_apps']==1 and checks['release_guards']==1 and checks['accessibility_owners']==1 and not checks['legacy_phase_apps'] and not checks['font_files_bundled'] else 'FAIL'
print(json.dumps(checks,indent=2))
if checks['status']!='PASS':sys.exit(1)
