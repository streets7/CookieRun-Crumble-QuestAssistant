// Run popup start with fake DOM/network: no browser or game is controlled.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(__dirname + '/web_ui.py', 'utf8');
const valueFunction = source.match(/^function values\(\).*$/m)[0];
const groupFunctions = source.slice(source.indexOf('function updateRunControls('), source.indexOf('async function nextAction('));
const labels = [...source.matchAll(/class="group-start"[^>]*>([^<]*)<\/button>/g)].map(m => m[1]);
assert.deepEqual(labels, ['시작', '시작', '시작', '시작', '시작']);

function scenario(fetchImpl) {
  const tasks = [
    {id: 'task_arena', type: 'checkbox', checked: true},
    {id: 'task_coin_dungeon', type: 'checkbox', checked: true},
  ];
  const buttons = [{disabled: false}, {disabled: false}];
  const state = {requests: [], alerts: [], closed: false};
  const ctx = vm.createContext({
    keys: ['task_arena', 'task_coin_dungeon', 'task_quest', 'infinite', 'cycles'],
    defaults: {task_quest: true, infinite: true, cycles: 100},
    groupStartPending: false, lastRunBusy: false,
    bossControlsPending: Promise.resolve(true),
    document: {
      // All main-start controls and hidden main inputs are intentionally absent.
      getElementById: id => tasks.find(t => t.id === id) || null,
      querySelectorAll: selector => selector === '.group-start' ? buttons : tasks,
    },
    alert: message => state.alerts.push(message),
    closeTaskPopup: () => {state.closed = true;},
    poll: async () => {},
    fetch: async (url, options) => {
      state.requests.push({url, data: JSON.parse(options.body)});
      return fetchImpl ? await fetchImpl() : {ok: true, json: async () => ({message: '시작했습니다.'})};
    },
  });
  vm.runInContext(valueFunction + '\n' + groupFunctions, ctx);
  return {ctx, state, tasks, buttons};
}

(async () => {
  let s = scenario();
  await s.ctx.startTaskGroup('challenge', ['task_arena'], '도전 던전');
  assert.equal(s.state.requests[0].url, '/start-group');
  assert.deepEqual(s.state.requests[0].data.selected_tasks, ['task_arena']);
  assert.equal(s.state.closed, true);
  assert.equal(s.tasks[1].checked, false);
  assert.equal(s.state.alerts.length, 0);

  s = scenario(); s.tasks[0].checked = false;
  await s.ctx.startTaskGroup('challenge', ['task_arena'], '도전 던전');
  assert.equal(s.state.requests.length, 0);
  assert.match(s.state.alerts[0], /하나 이상/);

  s = scenario(async () => {throw new Error('offline');});
  await s.ctx.startTaskGroup('challenge', ['task_arena'], '도전 던전');
  assert.match(s.state.alerts[0], /연결할 수 없습니다/);
  assert.equal(s.state.closed, false);
  assert.equal(s.tasks[1].checked, true);
  assert.ok(s.buttons.every(b => !b.disabled));

  s = scenario(async () => ({ok: false, json: async () => ({message: '제작 중'})}));
  await s.ctx.startTaskGroup('challenge', ['task_arena'], '도전 던전');
  assert.equal(s.state.closed, false);
  assert.deepEqual(s.state.alerts, ['제작 중']);

  let release;
  s = scenario(() => new Promise(resolve => {release = resolve;}));
  const first = s.ctx.startTaskGroup('challenge', ['task_arena'], '도전 던전');
  await s.ctx.startTaskGroup('challenge', ['task_arena'], '도전 던전');
  assert.equal(s.state.requests.length, 1);
  release({ok: true, json: async () => ({})});
  await first;

  s = scenario(); s.ctx.updateRunControls(true);
  await s.ctx.startTaskGroup('challenge', ['task_arena'], '도전 던전');
  assert.equal(s.state.requests.length, 0);
  assert.ok(s.buttons.every(b => b.disabled));
  console.log('6 popup scenarios passed; 5 start labels verified; no main controls required.');
})().catch(error => {console.error(error); process.exitCode = 1;});
