#!/usr/bin/env node
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('gateway/web/app.js', 'utf8');
const start = source.indexOf('function resolveSlashCommand(');
const end = source.indexOf('function renderCommands()', start);
assert(start >= 0 && end > start);
const context = vm.createContext({});
vm.runInContext(source.slice(start, end), context);
const commands = [
  {name: 'compact', category: 'native'},
  {name: 'Orbit Notes:compact', bare_name: 'compact', category: 'skill'},
  {name: 'Orbit Notes:review', bare_name: 'review', category: 'skill'},
  {name: ':review', bare_name: 'review', category: 'skill'},
  {name: 'repo.fetch', category: 'mcp'},
  {name: 'helpful', execution: 'local'},
];
const resolve = (text) => context.resolveSlashCommand(commands, text);
assert.equal(resolve('/compact instructions').category, 'native');
assert.equal(resolve('/Orbit Notes:compact instructions').category, 'skill');
assert.equal(resolve('/Orbit Notes:review\ncheck files').name, 'Orbit Notes:review');
assert.equal(resolve('/:review').name, ':review');
assert.equal(resolve('/review instructions').category, 'skill');
assert.equal(resolve('/repo.fetch https://example.invalid').category, 'mcp');
assert.equal(resolve('/compact-other'), undefined);
assert.equal(resolve('/missing'), undefined);
assert.equal(resolve('/helpful').execution, 'local');
assert.equal(resolve('/repo.fetching'), undefined);
console.log('PASS: production slash resolution preserves exact command precedence, scoped names with spaces, global skills, arguments and unknown-command rejection');
