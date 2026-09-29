const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

require('../../browser-helpers/douyin-sync/merge.js');

function scanCreatorPage(cards, bodyText = '作品管理') {
  const window = {};
  const nodes = cards.map(({ title, body, href, hidden = false }) => {
    const card = {
      innerText: `${title} ${body}`,
      parentElement: null,
      getClientRects: () => hidden ? [] : [{}],
      querySelector: () => href ? { href } : null,
    };
    return {
      innerText: title,
      parentElement: card,
      getClientRects: () => hidden ? [] : [{}],
    };
  });
  const document = {
    title: '抖音创作者中心',
    body: { innerText: bodyText },
    querySelectorAll: () => nodes,
  };
  const source = fs.readFileSync(require.resolve('../../browser-helpers/douyin-sync/scanner.js'), 'utf8');
  vm.runInNewContext(source, { window, document });
  return window.__easelDouyinScanVisible();
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

test('creator center login page, empty list, multiple works, missing metrics, and visible zeroes', () => {
  const login = scanCreatorPage([], '请登录后查看作品数据');
  assert.equal(login.loginPrompt, true);
  assert.equal(login.rows.length, 0);

  const empty = scanCreatorPage([]);
  assert.equal(empty.loginPrompt, false);

  const scanned = scanCreatorPage([
    { title: '猫咪抢窝', body: '发布时间 2026-09-20 12:30 视频时长 00:23 播放量 1.2万 点赞 0 评论 5 收藏 7 分享 2', href: 'https://creator.douyin.com/video/1001' },
    { title: '猫咪睡觉', body: '2026-09-21 播放量 18 点赞 3' },
    { title: '隐藏内容', body: '播放量 99 点赞 99', hidden: true },
  ]);
  assert.equal(scanned.rows.length, 2);
  assert.equal(scanned.rows[0].platform_post_id, '1001');
  assert.equal(scanned.rows[0].duration, 23);
  assert.equal(scanned.rows[0].views, 12000);
  assert.equal(scanned.rows[0].likes, 0);
  assert.equal(scanned.rows[1].comments, null);
  assert.equal(scanned.rows[1].favorites, null);
  assert.equal(scanned.rows[1].shares, null);
});
