const fs = require('fs');
const path = require('path');

const rendererJsDir = path.join(__dirname, '..', 'renderer', 'js');
const cssPath = path.join(__dirname, '..', 'renderer', 'css', 'beast-hacker-coherence.css');
const css = fs.readFileSync(cssPath, 'utf8');
const failures = [];

let braces = 0;
for (const char of css) {
  if (char === '{') braces += 1;
  if (char === '}') braces -= 1;
}
if (braces !== 0) failures.push(`stylesheet braces are unbalanced: ${braces}`);

const routeClasses = new Set();
function scanJavaScript(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const absolute = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      scanJavaScript(absolute);
      continue;
    }
    if (!entry.name.endsWith('.js')) continue;
    const source = fs.readFileSync(absolute, 'utf8');
    for (const match of source.matchAll(/beast-[a-z0-9-]+-page/g)) routeClasses.add(match[0]);
  }
}
scanJavaScript(rendererJsDir);
for (const route of [...routeClasses].sort()) {
  if (!css.includes(`.${route}`)) failures.push(`missing coherence selector for ${route}`);
}

for (const token of [
  '--hack-green-hot', '--hack-cyan', '--hack-muted',
  'background-clip: text', 'border-image: none',
  'overflow-wrap: anywhere', 'beast-console-pulse',
]) {
  if (!css.includes(token)) failures.push(`missing visual contract token: ${token}`);
}

if (failures.length) {
  console.error(failures.map(item => `FAIL ${item}`).join('\n'));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true, routes: routeClasses.size, stylesheet: 'balanced', contract: 'complete' }, null, 2));
