// Only fake DOM/network. Never contacts the running helper or game.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(__dirname + '/web_ui.py', 'utf8');
const script = source.slice(source.indexOf('<script>') + 8, source.indexOf('</script>'));
new vm.Script(script);
const sync = script.slice(script.indexOf('let bossControlsPending='), script.indexOf('async function saveSettings('));
const start = script.match(/^async function startRun\(.*$/m)[0];

function scenario(fetchImpl) {
  const inputs = {
    boss_keyboard_move_normal: {checked: true},
    boss_keyboard_move_corner: {checked: false},
    boss_preset_order: {value: ''},
  };
  const requests = [], alerts = [];
  const context = vm.createContext({
    document: {getElementById: id => inputs[id]},
    AbortSignal, alert: msg => alerts.push(msg), confirm: () => true,
    renderBossSettingsSummary: () => {},
    values: () => ({automatic_check: false}),
    fetch: async (url, options) => {
      requests.push({url, data: options.body ? JSON.parse(options.body) : null});
      return fetchImpl ? fetchImpl(url) : {ok: true};
    },
  });
  vm.runInContext(sync + '\n' + start, context);
  return {context, inputs, requests, alerts};
}

(async () => {
  for (const id of ['boss_keyboard_move_normal', 'boss_keyboard_move_corner']) {
    assert.match(source, new RegExp('id="' + id + '"[^>]*onchange="syncBossControls\\(\\)"'));
  }
  let s = scenario();
  await s.context.syncBossControls();
  assert.equal(s.requests[0].url, '/boss-controls');
  assert.equal(s.requests[0].data.boss_keyboard_move_normal, true);
  assert.equal(s.requests[0].data.boss_keyboard_move_corner, false);
  for (let n = 1; n <= 5; n++) assert.equal(s.requests[0].data['boss_preset_' + n], false);

  let release;
  s = scenario(url => url === '/boss-controls' && !release
    ? new Promise(resolve => {release = resolve;}) : {ok: true});
  const first = s.context.syncBossControls();
  await Promise.resolve();
  s.inputs.boss_keyboard_move_normal.checked = false;
  const second = s.context.syncBossControls();
  const starting = s.context.startRun();
  assert.equal(s.requests.length, 1);
  release({ok: true});
  await Promise.all([first, second, starting]);
  assert.deepEqual(s.requests.map(r => r.url), ['/boss-controls', '/boss-controls', '/start']);
  assert.equal(s.requests[1].data.boss_keyboard_move_normal, false);

  s = scenario(url => ({ok: url === '/stop'}));
  await s.context.syncBossControls();
  await s.context.startRun();
  assert.deepEqual(s.requests.map(r => r.url), ['/boss-controls', '/stop']);
  assert.equal(s.alerts.length, 1);
  console.log('Boss UI: explicit selections, ordered updates, start barrier and failure stop passed. Full UI syntax valid.');
})().catch(error => {console.error(error); process.exitCode = 1;});
