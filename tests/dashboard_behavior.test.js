// Runs the shipped inline script with a small DOM fixture and no network.
// This checks behavior, not browser layout; run browser QA separately.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'assets', 'dashboard.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function dashboard() {
  const elements = new Map();
  const listeners = new Map();
  const document = {
    activeElement: null,
    getElementById(id) {
      if (!elements.has(id)) {
        elements.set(id, {
          innerHTML: '', textContent: '', value: '', hidden: false,
          scrollTop: 0, scrollHeight: 8000, clientHeight: 500,
          classList: { toggle() {} },
          setAttribute() {},
          focus() { document.activeElement = this; },
        });
      }
      return elements.get(id);
    },
    querySelectorAll() { return []; },
    addEventListener(name, handler) { listeners.set(name, handler); },
  };
  const context = vm.createContext({ document, window: {} });
  vm.runInContext(script, context);
  const feed = document.getElementById('messages-list');
  return {
    context, document, feed,
    run(code) { return vm.runInContext(code, context); },
    ids() { return Array.from(feed.innerHTML.matchAll(/id="msg-(\d+)"/g), m => Number(m[1])); },
    click(action) {
      assert.ok(feed.innerHTML.includes(`data-action="${action}"`), `Missing ${action} control`);
      listeners.get('click')({ target: { closest: () => ({ dataset: { action } }) } });
    },
  };
}

function state(count = 241) {
  return {
    projects: [{ id: 'alpha', name: 'Alpha', status: 'active' }, { id: 'beta', name: 'Beta', status: 'active' }],
    messages: Array.from({ length: count }, (_, i) => ({
      id: i + 1, sender: 'tester', project_id: i % 2 ? 'beta' : 'alpha',
      channel: i % 3 ? 'general' : 'reviews', content: `Message ${i + 1} @human`,
    })),
  };
}

test('loading earlier messages keeps at most 80 cards', () => {
  const ui = dashboard();
  ui.context.renderState(state());
  assert.equal(ui.ids().length, 80);
  ui.click('load-earlier');
  assert.equal(ui.ids().length, 80);
  assert.deepEqual(ui.ids(), Array.from({ length: 80 }, (_, i) => i + 82));
});

test('new messages do not jump a reader who scrolled away from the bottom', () => {
  const ui = dashboard();
  ui.context.renderState(state());
  const before = ui.ids();
  ui.feed.scrollTop = 300;
  ui.context.renderState(state(242));
  assert.equal(ui.feed.scrollTop, 300);
  assert.deepEqual(ui.ids(), before);
});

test('earlier and newer pages cover the entire backlog without gaps', () => {
  const ui = dashboard();
  ui.context.renderState(state());
  const seen = new Set(ui.ids());
  while (ui.feed.innerHTML.includes('data-action="load-earlier"')) {
    ui.click('load-earlier');
    assert.ok(ui.ids().length <= 80);
    for (const id of ui.ids()) seen.add(id);
  }
  assert.deepEqual([...seen].sort((a, b) => a - b), Array.from({ length: 241 }, (_, i) => i + 1));
  while (ui.feed.innerHTML.includes('data-action="load-newer"')) {
    ui.click('load-newer');
    assert.ok(ui.ids().length <= 80);
  }
  assert.equal(ui.ids().at(-1), 241);
});

test('an older page stays anchored on refresh and can jump to latest', () => {
  const ui = dashboard();
  ui.context.renderState(state());
  ui.click('load-earlier');
  const before = ui.ids();
  ui.feed.scrollTop = 120;
  ui.context.renderState(state(245));
  assert.deepEqual(ui.ids(), before);
  assert.equal(ui.feed.scrollTop, 120);
  ui.click('show-latest');
  assert.equal(ui.ids().length, 80);
  assert.equal(ui.ids().at(-1), 245);
  assert.equal(ui.feed.scrollTop, ui.feed.scrollHeight);
});

test('the live tail follows new messages when already at the bottom', () => {
  const ui = dashboard();
  ui.context.renderState(state());
  ui.feed.scrollTop = ui.feed.scrollHeight - ui.feed.clientHeight;
  ui.context.renderState(state(242));
  assert.equal(ui.ids().length, 80);
  assert.equal(ui.ids().at(-1), 242);
  assert.equal(ui.feed.scrollTop, ui.feed.scrollHeight);
});

test('search finds old messages and clearing it resets to the latest page', () => {
  const ui = dashboard();
  ui.context.renderState(state());
  ui.click('load-earlier');
  const search = ui.document.getElementById('chat-search');
  search.value = 'Message 1 @human';
  ui.context.onSearchInput();
  assert.deepEqual(ui.ids(), [1]);
  search.value = '';
  ui.context.onSearchInput();
  assert.equal(ui.ids().length, 80);
  assert.equal(ui.ids().at(-1), 241);
});

test('project, channel, and needs-input filters reset paging', () => {
  const ui = dashboard();
  const data = state();
  ui.context.renderState(data);
  ui.click('load-earlier');
  ui.context.selectProject('beta');
  assert.deepEqual(ui.ids(), data.messages.filter(m => m.project_id === 'beta').slice(-80).map(m => m.id));
  ui.click('load-earlier');
  ui.context.selectChannel('reviews');
  assert.deepEqual(ui.ids(), data.messages.filter(m => m.project_id === 'beta' && m.channel === 'reviews').slice(-80).map(m => m.id));
  ui.context.selectProject('');
  ui.context.selectChannel('all');
  ui.click('load-earlier');
  ui.context.toggleNeedsMeFilter();
  assert.equal(ui.ids().length, 80);
  assert.equal(ui.ids().at(-1), 241);
});

test('refresh preserves composer focus and draft', () => {
  const ui = dashboard();
  ui.context.renderState(state());
  const composer = ui.document.getElementById('post-content');
  composer.value = 'Unfinished draft';
  composer.focus();
  ui.context.renderState(state(242));
  assert.equal(ui.document.activeElement, composer);
  assert.equal(composer.value, 'Unfinished draft');
});

test('empty and short feeds render without paging controls', () => {
  const ui = dashboard();
  for (const count of [0, 1, 79, 80]) {
    ui.context.renderState(state(count));
    assert.equal(ui.ids().length, count);
    assert.ok(!ui.feed.innerHTML.includes('data-action="load-earlier"'));
    assert.ok(!ui.feed.innerHTML.includes('data-action="load-newer"'));
  }
});

test('the Needs My Input count matches the channel scope of the feed', () => {
  const ui = dashboard();
  ui.context.renderState({
    projects: [{ id: 'alpha', name: 'Alpha', status: 'active' }],
    messages: [
      { id: 1, sender: 'codex', project_id: 'alpha', channel: 'general', content: 'plain note' },
      { id: 2, sender: 'codex', project_id: 'alpha', channel: 'tasks', content: 'waiting on owner' },
    ],
  });
  assert.equal(ui.document.getElementById('needs-me-count').textContent, 1);
  ui.context.selectChannel('general');
  assert.equal(ui.document.getElementById('needs-me-count').textContent, 0);
  ui.context.selectChannel('tasks');
  assert.equal(ui.document.getElementById('needs-me-count').textContent, 1);
  assert.equal(ui.ids().length, 1);
});

test('an empty view distinguishes an empty board from a filter hiding messages', () => {
  const ui = dashboard();
  ui.context.renderState({ projects: [{ id: 'alpha', name: 'Alpha', status: 'active' }], messages: [] });
  assert.match(ui.feed.innerHTML, /No messages on this board yet/);
  ui.context.renderState({
    projects: [{ id: 'alpha', name: 'Alpha', status: 'active' }],
    messages: [{ id: 1, sender: 'codex', project_id: 'alpha', channel: 'general', content: 'plain note' }],
  });
  ui.context.selectChannel('tasks');
  assert.match(ui.feed.innerHTML, /No messages match this view/);
  assert.ok(!ui.feed.innerHTML.includes('No messages on this board yet'));
});

test('day dividers separate days and appear once per day', () => {
  const ui = dashboard();
  const daysAgo = (offset) => new Date(Date.now() - offset * 86400000).toISOString();
  ui.context.renderState({
    projects: [{ id: 'alpha', name: 'Alpha', status: 'active' }],
    messages: [
      { id: 1, sender: 'codex', project_id: 'alpha', channel: 'general', content: 'two days ago', created_at: daysAgo(2) },
      { id: 2, sender: 'codex', project_id: 'alpha', channel: 'general', content: 'also two days ago', created_at: daysAgo(2) },
      { id: 3, sender: 'codex', project_id: 'alpha', channel: 'general', content: 'yesterday', created_at: daysAgo(1) },
      { id: 4, sender: 'codex', project_id: 'alpha', channel: 'general', content: 'today', created_at: daysAgo(0) },
    ],
  });
  assert.equal((ui.feed.innerHTML.match(/class="day-divider"/g) || []).length, 3);
  assert.ok(ui.feed.innerHTML.includes('<span>Yesterday</span>'));
  assert.ok(ui.feed.innerHTML.includes('<span>Today</span>'));
  // A stamp is a clock time only; the divider carries the date.
  assert.ok(!ui.feed.innerHTML.includes('Nov '));
});

test('tag chips follow the live roster instead of a hardcoded list', () => {
  const ui = dashboard();
  ui.context.renderState({
    projects: [{ id: 'alpha', name: 'Alpha', status: 'active' }],
    messages: [],
    agents: [{ id: 'codex' }, { id: 'opus-bedrock' }, { id: 'human-director' }],
  });
  const chips = ui.document.getElementById('mention-chips').innerHTML;
  assert.ok(chips.includes('data-mention="@all"'));
  assert.ok(chips.includes('data-mention="@codex"'));
  assert.ok(chips.includes('data-mention="@opus-bedrock"'));
  assert.ok(!chips.includes('@claude'));
  assert.ok(!chips.includes('@human-director'));
});

