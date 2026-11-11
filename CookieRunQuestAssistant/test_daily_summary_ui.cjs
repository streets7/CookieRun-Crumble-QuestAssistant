const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(__dirname + '/web_ui.py', 'utf8');
const script = source.slice(source.indexOf('<script>') + 8, source.indexOf('</script>'));
new vm.Script(script);

const start = script.indexOf('let lastDailySummary=');
const end = script.indexOf('async function adminLogin');
assert.ok(start >= 0 && end > start, 'daily summary UI functions must exist');
const dailyFunctions = script.slice(start, end);
const elements = {};
for (const id of ['dailySummaryTitle','dailySummaryMeta','dailyRuns','dailyCompleted','dailyErrors','dailyRecoveries','dailySummaryTasks','dailySummaryArena','dailySummaryActivities','dailySummaryDeploy']) {
  elements[id] = {textContent: '', innerHTML: ''};
}
let copied = '';
const context = vm.createContext({
  document: {getElementById: id => elements[id]},
  esc: value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
  copyText: async text => {copied = text;},
});
vm.runInContext(dailyFunctions, context);

const summary = {
  date: '2026-11-11', version: 'v15.18', status: '실행 완료',
  runs: 2, completed: 7, errors: 1, recoveries: 3,
  tasks: {'현재 퀘스트 자동 완료': 2, '아레나 모드': 1},
  activities: [{time:'10:10:00', text:'<script>bad()</script>'}],
  arena: [{time:'10:09:00', deck:2, mine:32350000, opponent:35750000, result:'조건 미충족'}],
  deployment: {mac:'검증 완료', windows:'실제 실행 검증 필요', github:'저장소 연결 필요'},
};
context.renderDailySummary(summary);
assert.equal(elements.dailyRuns.textContent, '2회');
assert.equal(elements.dailyCompleted.textContent, '7개');
assert.match(elements.dailySummaryTasks.innerHTML, /현재 퀘스트 자동 완료/);
assert.match(elements.dailySummaryArena.innerHTML, /2번 덱/);
assert.match(elements.dailySummaryArena.innerHTML, /32\.35M/);
assert.doesNotMatch(elements.dailySummaryActivities.innerHTML, /<script>/);
assert.match(elements.dailySummaryActivities.innerHTML, /&lt;script&gt;/);
assert.match(elements.dailySummaryDeploy.innerHTML, /Windows/);

(async () => {
  await context.copyDailySummary();
  assert.match(copied, /2026-11-11 오늘의 총정리/);
  assert.match(copied, /실행 2회 · 완료 7개 · 오류 1건 · 복구 3회/);
  assert.match(copied, /2번 덱/);
  console.log('Daily summary popup: rendering, escaping, arena rows and copy text passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});
