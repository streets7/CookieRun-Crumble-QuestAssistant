// Static UI policy test. No browser or game is controlled.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const source=fs.readFileSync(__dirname+'/web_ui.py','utf8');
const placement=source.match(/^function placeHelpBesideText\(.*$/m)[0];
const hover=source.match(/^function setupHoverHelp\(.*$/m)[0];
assert.match(placement,/task-help.*task-group-name/);
assert.match(placement,/screen-size-note/);
assert.match(placement,/channel-notice/);
assert.match(placement,/coordinate-note/);
assert.match(hover,/x=r\.right\+10/);
assert.match(hover,/tooltip\.style\.left=x\+'px'/);
assert.doesNotMatch(hover,/r\.left-w-10/);
assert.match(hover,/window\.innerWidth-x-8/);
console.log('Hover help: icons follow text and tooltips stay on the right.');
