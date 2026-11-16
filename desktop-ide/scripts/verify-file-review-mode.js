'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ctx = vm.createContext({window:{}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../renderer/js/ai/mode-controller.js'),'utf8'),ctx);
const mode = ctx.window.BeastAICodingModules.createModeController({api:{},constants:{}});
assert.equal(mode.isAgentAnalysisPrompt('Review the file. Do not modify files or run tests.'),true);
assert.equal(mode.isAgentAnalysisPrompt('Review the file and fix the bug. Do not run tests.'),false);
assert.equal(mode.isAgentAnalysisPrompt("Audit the file without modifying it."),true);
assert.doesNotMatch(mode.instructionFor('review','Find defects',['a.py']),/Return BEAST Action IR/);
console.log('File review mode checks passed.');
