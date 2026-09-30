// Executed only in the active creator.douyin.com tab after the user clicks Scan.
window.__easelDouyinInspect = () => {
  const body = document.body?.innerText || '';
  const loginPrompt = /\/login|\/passport|请登录|扫码登录|登录抖音|登录后/.test(`${location.pathname} ${body.slice(0, 1200)}`)
    && !document.querySelector("[class*='info-title-text'], [class*='info-title-operation']");
  const pageLabel = /作品管理|内容管理|视频列表/.test(body);
  const supportedPage = !loginPrompt && (location.pathname.includes('/content/manage') || pageLabel);
  return { loginPrompt, supportedPage, pageTitle: document.title, path: location.pathname };
};

window.__easelDouyinScanVisible = () => {
  const visible = (node) => Boolean(node?.getClientRects?.().length);
  const text = (node) => (node?.innerText || node?.textContent || '').replace(/\s+/g, ' ').trim();
  const valueFor = (body, label) => {
    const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const match = body.match(new RegExp(`${escaped}\\s*[:：]?\\s*([\\d,.]+\\s*[万wW]?)`));
    if (!match) return null;
    const raw = match[1].replace(/[\s,]/g, '').toLowerCase();
    const multiplier = raw.endsWith('万') || raw.endsWith('w') ? 10000 : 1;
    const number = Number.parseFloat(raw.replace(/[万w]$/, ''));
    return Number.isFinite(number) ? Math.round(number * multiplier) : null;
  };
  const cardFor = (titleNode) => {
    let card = titleNode;
    for (let depth = 0; depth < 9 && card; depth += 1, card = card.parentElement) {
      const body = text(card);
      if (/播放/.test(body) && (/点赞/.test(body) || /评论/.test(body))) return card;
    }
    return titleNode.parentElement;
  };
  // The operation wrapper also contains controls and has different text from the
  // title. Matching it as a second candidate created phantom posts in the real UI.
  const candidates = [...document.querySelectorAll("[class*='info-title-text']")];
  const rows = [];
  const seenCards = new Set();
  for (const titleNode of candidates) {
    if (!visible(titleNode)) continue;
    const title = text(titleNode).split('\n')[0]
      .replace(/\s*编辑作品\s*设置权限\s*作品置顶\s*删除作品\s*$/, '').trim().slice(0, 1000);
    if (!title) continue;
    const card = cardFor(titleNode);
    if (seenCards.has(card)) continue;
    seenCards.add(card);
    const body = text(card);
    const href = card?.querySelector("a[href*='/video/'], a[href*='/note/']")?.href || '';
    const idMatch = href.match(/\/(?:video|note)\/(\d+)/);
    const dateMatch = body.match(/(20\d{2}年\d{1,2}月\d{1,2}日(?:\s+\d{1,2}:\d{2})?|20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}(?:\s+\d{1,2}:\d{2})?)/);
    const durationMatch = body.match(/(?:时长|视频时长)\s*[:：]?\s*(\d{1,2}:\d{2})/);
    let duration = null;
    if (durationMatch) {
      const parts = durationMatch[1].split(':').map(Number);
      duration = parts.length === 2 ? parts[0] * 60 + parts[1] : null;
    }
    rows.push({
      platform_post_id: idMatch?.[1] || null,
      title,
      publish_time: null,
      publish_time_raw: dateMatch?.[1] || null,
      duration,
      views: valueFor(body, '播放量') ?? valueFor(body, '播放'),
      likes: valueFor(body, '点赞'),
      comments: valueFor(body, '评论'),
      favorites: valueFor(body, '收藏'),
      shares: valueFor(body, '分享'),
    });
  }
  const controls = [...document.querySelectorAll('button,[role="button"],a,[aria-label],[title]')]
    .filter((node) => visible(node));
  const controlLabel = (node) => `${text(node)} ${node.getAttribute?.('aria-label') || ''} ${node.title || ''}`.trim();
  const next = controls.find((node) => /下一页|下页|后页|next/i.test(controlLabel(node))
    && node.getAttribute?.('aria-disabled') !== 'true' && !node.disabled);
  const disabledNext = controls.some((node) => /下一页|下页|后页|next/i.test(controlLabel(node))
    && (node.disabled || node.getAttribute?.('aria-disabled') === 'true'));
  const pageLabel = [...document.querySelectorAll('button,[role="button"],li,span')]
    .find((node) => node.getAttribute?.('aria-current') === 'page' || /active|current|selected/.test(node.className || ''));
  const pageNumber = text(pageLabel);
  const rowKeys = rows.map((row) => row.platform_post_id || `${row.publish_time_raw || row.publish_time || ''}\0${row.title}`).sort();
  const fingerprint = `${location.pathname}|${pageNumber}|${rowKeys.join('|')}`.slice(0, 500);
  const pageBody = document.body?.innerText || '';
  const explicitEnd = /没有更多作品|没有更多内容/.test(pageBody);
  const totalMatch = pageBody.match(/作品\s*[（(]\s*(\d+)\s*[）)]/);
  const expectedCount = totalMatch ? Number.parseInt(totalMatch[1], 10) : null;
  return {
    rows,
    pageTitle: document.title,
    loginPrompt: /登录/.test(document.body?.innerText || '') && rows.length === 0,
    fingerprint,
    pageNumber,
    hasNext: Boolean(next) || (!disabledNext && !explicitEnd),
    explicitEnd,
    nextLabel: next ? controlLabel(next) : '',
    expectedCount: Number.isFinite(expectedCount) ? expectedCount : null,
  };
};
