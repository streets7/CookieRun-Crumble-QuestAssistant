const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(__dirname + '/web_ui.py', 'utf8');
const script = source.slice(source.indexOf('<script>') + 8, source.indexOf('</script>'));
new vm.Script(script);

assert.match(source, /id="integrated_automation"/);
assert.match(source, /통합 자동 순환/);
assert.match(source, /같은 스테이지 5회 반복/);
assert.match(source, /"integrated_automation": False/);
assert.match(script, /'integrated_automation'/);
assert.match(source, /id="integratedAutomationStatus"/);
assert.match(script, /summary\??\.integrated_automation/);

const pollGuardMatch = script.match(/function isCurrentAdminPoll\([^}]+\}/);
assert.ok(pollGuardMatch, 'admin poll generation guard must exist');
const context = {};
vm.runInNewContext(pollGuardMatch[0] + ';this.guard=isCurrentAdminPoll;', context);
assert.equal(context.guard('old-token', 'new-token'), false);
assert.equal(context.guard('new-token', 'new-token'), true);
const hideGuardMatch = script.match(/function canHideFeature\([^}]+\}/);
assert.ok(hideGuardMatch, 'execution log visibility guard must exist');
vm.runInNewContext(hideGuardMatch[0] + ';this.canHide=canHideFeature;', context);
assert.equal(context.canHide('card_adminLogs'), false);
assert.equal(context.canHide('card_settingsCard'), true);

console.log('Integrated automation UI: five repeats, persistence, admin status and stale poll guard passed.');
