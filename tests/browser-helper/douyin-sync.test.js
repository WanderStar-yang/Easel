const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

require('../../browser-helpers/douyin-sync/merge.js');

function scanCreatorPage(cards, bodyText = '作品管理', pathname = '/creator-micro/content/manage', controls = []) {
  const window = {};
  const nodes = cards.flatMap(({ title, body, href, hidden = false }) => {
    const card = {
      innerText: `${title} ${body}`,
      parentElement: null,
      getClientRects: () => hidden ? [] : [{}],
      querySelector: () => href ? { href } : null,
    };
    return [{
      innerText: title,
      className: 'info-title-text-test',
      parentElement: card,
      getClientRects: () => hidden ? [] : [{}],
    }, {
      innerText: `${title} 编辑作品 设置权限 删除作品`,
      className: 'info-title-operation-test',
      parentElement: card,
      getClientRects: () => hidden ? [] : [{}],
    }];
  });
  const document = {
    title: '抖音创作者中心',
    body: { innerText: bodyText },
    querySelectorAll: (selector) => selector.includes('info-title-text')
      ? nodes.filter((node) => node.className.includes('info-title-text'))
      : selector.includes('info-title-operation') ? nodes.filter((node) => node.className.includes('info-title-operation'))
        : controls,
    querySelector: () => null,
  };
  const source = fs.readFileSync(require.resolve('../../browser-helpers/douyin-sync/scanner.js'), 'utf8');
  vm.runInNewContext(source, { window, document, location: { pathname } });
  return { ...window.__easelDouyinScanVisible(), pageState: window.__easelDouyinInspect() };
}

test('scans accumulated across pages merge repeated cards without dropping new posts', () => {
  const pageOne = [
    { platform_post_id: 'aweme-1', title: '作品一', views: 10 },
    { title: '无 ID 作品', publish_time: '2025-01-01', views: 2 },
  ];
  const pageTwo = [
    { platform_post_id: 'aweme-1', title: '作品一', views: 12 },
    { platform_post_id: 'aweme-2', title: '作品二', views: 0 },
    { title: '无 ID 作品', publish_time: '2025-01-01', views: 3 },
  ];
  const merged = EaselDouyinSync.mergeRows(pageOne, pageTwo);
  assert.equal(merged.length, 3);
  assert.equal(merged.find((row) => row.platform_post_id === 'aweme-1').views, 12);
  assert.equal(merged.find((row) => row.platform_post_id === 'aweme-2').views, 0);
  assert.equal(merged.filter((row) => row.title === '无 ID 作品').length, 1);
});

test('two-stage dedup prefers platform IDs and normalizes title and date fallback', () => {
  const merged = EaselDouyinSync.mergeRows([], [
    { title: ' 猫咪　日常 ', publish_time: '2025/01/02', views: 3 },
    { platform_post_id: 'aweme-a', title: '猫咪 日常', publish_time: '2025-01-02', views: 4 },
    { platform_post_id: 'aweme-a', title: '猫咪日常', publish_time: '2025-01-02', likes: 1 },
    { platform_post_id: 'aweme-b', title: '猫咪日常', publish_time: '2025-01-02', views: 8 },
  ]);
  assert.equal(merged.length, 2);
  assert.deepEqual(merged.map((row) => row.platform_post_id).sort(), ['aweme-a', 'aweme-b']);
  assert.equal(merged.find((row) => row.platform_post_id === 'aweme-a').views, 4);
  assert.equal(merged.find((row) => row.platform_post_id === 'aweme-a').likes, 1);
  assert.deepEqual(EaselDouyinSync.counts([
    { platform_post_id: '1' }, { platform_post_id: '1' }, { platform_post_id: '2' },
  ], 4), { rawCount: 4, uniqueCount: 2, duplicateCount: 2 });
});

test('creator center login page, empty list, multiple works, missing metrics, and visible zeroes', () => {
  const login = scanCreatorPage([], '请登录后查看作品数据');
  assert.equal(login.loginPrompt, true);
  assert.equal(login.pageState.loginPrompt, true);
  assert.equal(login.rows.length, 0);

  const empty = scanCreatorPage([]);
  assert.equal(empty.loginPrompt, false);
  assert.equal(empty.pageState.supportedPage, true);
  assert.equal(scanCreatorPage([], '首页内容', '/creator-micro/home').pageState.supportedPage, false);

  const scanned = scanCreatorPage([
    { title: '猫咪抢窝', body: '发布时间 2026-09-20 12:30 视频时长 00:23 播放量 1.2万 点赞 0 评论 5 收藏 7 分享 2', href: 'https://creator.douyin.com/video/1001' },
    { title: '猫咪睡觉', body: '2025年11月11日 09:46 播放量 18 点赞 3' },
    { title: '隐藏内容', body: '播放量 99 点赞 99', hidden: true },
  ]);
  assert.equal(scanned.rows.length, 2);
  assert.equal(scanned.rows[0].platform_post_id, '1001');
  assert.equal(scanned.rows[0].title, '猫咪抢窝');
  assert.equal(scanned.rows[0].duration, 23);
  assert.equal(scanned.rows[0].views, 12000);
  assert.equal(scanned.rows[0].likes, 0);
  assert.equal(scanned.rows[1].comments, null);
  assert.equal(scanned.rows[1].favorites, null);
  assert.equal(scanned.rows[1].shares, null);
  assert.equal(scanned.rows[1].publish_time, null);
  assert.equal(scanned.rows[1].publish_time_raw, '2025年11月11日 09:46');
});

test('same title on different cards stays distinct when platform IDs differ', () => {
  const scanned = scanCreatorPage([
    { title: '同名作品', body: '2026-09-20 播放量 10 点赞 1', href: 'https://creator.douyin.com/video/2001' },
    { title: '同名作品', body: '2026-09-20 播放量 20 点赞 2', href: 'https://creator.douyin.com/video/2002' },
  ]);
  assert.equal(scanned.rows.length, 2);
  assert.deepEqual(Array.from(scanned.rows, (row) => row.platform_post_id), ['2001', '2002']);
});

test('pagination is complete only when a visible next control is explicitly disabled', () => {
  const enabled = scanCreatorPage([], '作品管理', '/creator-micro/content/manage', [
    { innerText: '下一页', disabled: false, title: '', getClientRects: () => [{}], getAttribute: () => null },
  ]);
  assert.equal(enabled.hasNext, true);
  assert.equal(enabled.nextLabel.trim(), '下一页');

  const lastPage = scanCreatorPage([], '作品管理', '/creator-micro/content/manage', [
    { innerText: '下一页', disabled: true, title: '', getClientRects: () => [{}], getAttribute: () => null },
  ]);
  assert.equal(lastPage.hasNext, false);

  const unsupportedPagination = scanCreatorPage([]);
  assert.equal(unsupportedPagination.hasNext, true);
  assert.equal(unsupportedPagination.nextLabel, '');

  const explicitLastPage = scanCreatorPage([], '作品管理 没有更多作品');
  assert.equal(explicitLastPage.explicitEnd, true);
  assert.equal(explicitLastPage.hasNext, false);

  const countedPage = scanCreatorPage([], '作品 (83) 没有更多作品');
  assert.equal(countedPage.expectedCount, 83);
  assert.equal(countedPage.hasNext, false);
});

test('returning a completed scan for preview does not overwrite its terminal session state', async () => {
  const source = fs.readFileSync(require.resolve('../../browser-helpers/douyin-sync/popup.js'), 'utf8');
  const elements = new Map();
  const calls = [];
  const window = { __easelDouyinInspect: () => ({ loginPrompt: false, supportedPage: true }) };
  for (const id of ['#session', '#base', '#status', '#detect', '#scan', '#pause', '#resume', '#end', '#cancel', '#submit']) {
    elements.set(id, { value: id === '#session' ? 'session-token' : '', disabled: false, addEventListener() {} });
  }
  elements.get('#session').value = 'session-token';
  elements.get('#base').value = 'http://localhost:7860';
  elements.get('#submit').addEventListener = (event, callback) => { elements.get('#submit').click = callback; };
  const document = { querySelector: (selector) => elements.get(selector) };
  const chrome = {
    tabs: { query: async () => [{ id: 1, url: 'https://creator.douyin.com/creator-micro/content/manage' }] },
    scripting: { executeScript: async (options) => options.files
      ? [] : [{ result: { loginPrompt: false, supportedPage: true } }] },
    storage: { local: { get: async () => ({ base: 'http://localhost:7860' }), set: async () => {} } },
  };
  const fetch = async (url, options = {}) => {
    calls.push({ url, method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : null });
    if ((options.method || 'GET') === 'GET') {
      return { ok: true, json: async () => ({ status: 'scan_completed', unique_count: 83,
        raw_observation_count: 83, duplicate_count: 0, pages_scanned: 2 }) };
    }
    if (url.endsWith('/preview')) {
      return { ok: true, json: async () => ({ status: 'preview_ready', preview: { snapshot_complete: true,
        platform_unique_count: 83, raw_observation_count: 83, scan_duplicate_count: 0 } }) };
    }
    return { ok: true, json: async () => ({ status: 'ready_to_scan' }) };
  };
  vm.runInNewContext(source, { document, window, chrome, fetch, URL, Error, console, setTimeout, clearTimeout });
  elements.get('#submit').click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(calls.some((call) => call.url.endsWith('/preview') && call.method === 'POST'), true);
  assert.equal(calls.some((call) => call.url.endsWith('/extension-state') && call.method === 'POST'), false);
});

test('a reopened popup completes a pending end request before generating preview', async () => {
  const source = fs.readFileSync(require.resolve('../../browser-helpers/douyin-sync/popup.js'), 'utf8');
  const elements = new Map();
  const calls = [];
  const window = { __easelDouyinInspect: () => ({ loginPrompt: false, supportedPage: true }) };
  for (const id of ['#session', '#base', '#status', '#detect', '#scan', '#pause', '#resume', '#end', '#cancel', '#submit']) {
    elements.set(id, { value: id === '#session' ? 'session-token' : '', disabled: false, addEventListener() {} });
  }
  elements.get('#base').value = 'http://localhost:7860';
  elements.get('#submit').addEventListener = (event, callback) => { elements.get('#submit').click = callback; };
  const document = { querySelector: (selector) => elements.get(selector) };
  const chrome = {
    tabs: { query: async () => [{ id: 1, url: 'https://creator.douyin.com/creator-micro/content/manage' }] },
    scripting: { executeScript: async (options) => options.files
      ? [] : [{ result: { loginPrompt: false, supportedPage: true } }] },
    storage: { local: { get: async () => ({ base: 'http://localhost:7860' }), set: async () => {} } },
  };
  const fetch = async (url, options = {}) => {
    const method = options.method || 'GET';
    calls.push({ url, method, body: options.body ? JSON.parse(options.body) : null });
    if (method === 'GET') {
      return { ok: true, json: async () => ({ status: 'end_requested', source_url: 'https://creator.douyin.com/creator-micro/content/manage' }) };
    }
    if (url.endsWith('/preview')) {
      return { ok: true, json: async () => ({ status: 'preview_ready', preview: { snapshot_complete: false,
        platform_unique_count: 12, raw_observation_count: 12, scan_duplicate_count: 0 } }) };
    }
    return { ok: true, json: async () => ({ status: 'ended' }) };
  };
  vm.runInNewContext(source, { document, window, chrome, fetch, URL, Error, console, setTimeout, clearTimeout });
  elements.get('#submit').click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(calls.some((call) => call.url.endsWith('/extension-state') && call.body.status === 'ended'), true);
  assert.equal(calls.some((call) => call.url.endsWith('/preview') && call.method === 'POST'), true);
  assert.match(elements.get('#status').textContent, /已扫描内容预览/);
});
