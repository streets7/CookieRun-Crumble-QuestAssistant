const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(__dirname + '/web_ui.py', 'utf8');
const script = source.slice(source.indexOf('<script>') + 8, source.indexOf('</script>'));
new vm.Script(script);

assert.match(source, /id="integrated_automation"/);
assert.match(source, /통합 자동 순환/);
assert.match(source, /스테이지 정체 3분/);
assert.match(source, /"integrated_automation": False/);
assert.match(source, /"integrated_stall_seconds": 180/);
assert.match(script, /'integrated_automation'/);
assert.match(source, /id="integratedAutomationStatus"/);
assert.match(script, /summary\??\.integrated_automation/);

console.log('Integrated automation UI: control, fixed threshold, persistence and admin status passed.');
