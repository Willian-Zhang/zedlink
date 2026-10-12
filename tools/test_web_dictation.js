#!/usr/bin/env node
// Exercise production speech callbacks without requiring a microphone or speech service.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('gateway/web/app.js', 'utf8');
const start = source.indexOf('let speech = null;');
const end = source.indexOf('$("dictate-prompt").addEventListener', start);
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    value: '', maxLength: 3000, disabled: false, textContent: '', attrs: {},
    classList: { toggle() {}, add() {} },
    setAttribute(name, value) { this.attrs[name] = value; },
    dispatchEvent() {}, focus() { this.focused = true; }
  });
  return elements.get(id);
}
let recognizer;
let epoch = 'one';
class Recognition {
  start() { recognizer = this; this.onstart?.(); }
  stop() { this.stopped = true; }
  abort() { this.aborted = true; this.onend?.(); }
}
const context = vm.createContext({
  $: element, window: { webkitSpeechRecognition: Recognition },
  document: { querySelector: () => element('tools') },
  state: { capabilities: ['terminal.input'] },
  safeStore: { read: () => 'true', write() {} },
  baseThreadParams: () => ({ epoch }), terminalLiveInput: false,
  navigator: { language: 'en-US' }, notice() {}, Event: class {}, confirm: () => true
});
vm.runInContext(source.slice(start, end), context);
const result = (text, isFinal) => ({ 0: { transcript: text }, length: 1, isFinal });
function emit(...results) {
  const list = { length: results.length };
  results.forEach((value, index) => { list[index] = value; });
  recognizer.onresult({ results: list });
}
context.dictateInto('prompt');
assert.match(element('dictation-status').textContent, /Listening/);
emit(result('hello', false));
assert.equal(element('prompt').value, 'hello');
emit(result('hello world', true), result('again', false));
assert.equal(element('prompt').value, 'hello world again');
context.dictateInto('prompt');
assert.equal(recognizer.stopped, true);
assert.equal(recognizer.aborted, undefined);
emit(result('hello world', true), result('again!', true));
recognizer.onend();
assert.equal(element('prompt').value, 'hello world again!');
assert.equal(element('dictate-prompt').attrs['aria-pressed'], 'false');
context.dictateInto('prompt');
element('prompt').value = 'my edited draft';
emit(result('do not overwrite', true));
assert.equal(element('prompt').value, 'my edited draft');
assert.equal(recognizer.aborted, true);
context.dictateInto('prompt');
epoch = 'two';
emit(result('wrong session', true));
assert.equal(element('prompt').value, 'my edited draft');
context.dictateInto('prompt');
recognizer.onend();
assert.match(element('dictation-status').textContent, /No text returned/);
context.dictateInto('prompt');
recognizer.onerror({ error: 'network' });
recognizer.onend();
assert.match(element('dictation-status').textContent, /could not connect/);
context.window.webkitSpeechRecognition = undefined;
context.dictateInto('prompt');
assert.equal(element('prompt').focused, true);
assert.match(element('dictation-status').textContent, /does not support/);
console.log('PASS: noniterable results, interim updates, multiple final results, Stop finalization, draft/session guards, empty/error feedback and keyboard fallback');
