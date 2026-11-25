const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { runInNewContext } = require('node:vm');
const assert = require('node:assert/strict');
const test = require('node:test');

test('desktop composer requires a one-shot slash command for mutation', () => {
  const context = { window: {} };
  runInNewContext(readFileSync(join(__dirname, '../renderer/js/ai/agent-client.js'), 'utf8'), context);
  const parse = context.window.BeastAICodingModules.parseComposerPrompt;
  const plain = parse('Fix the typo');
  assert.equal(plain.mode, 'ask');
  for (const mode of ['ask', 'edit', 'agent']) {
    const request = parse(`/${mode}   Fix the typo`);
    assert.equal(request.mode, mode);
    assert.equal(request.prompt, 'Fix the typo');
  }
  assert.equal(parse('Another question').mode, 'ask');
  assert.throws(() => parse('/edit'), /task/i);
});
