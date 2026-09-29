// Executed only in the active creator.douyin.com tab after the user clicks Scan.
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
  const candidates = [...document.querySelectorAll("[class*='info-title-text'], [class*='info-title-operation']")];
  const rows = [];
  const seen = new Set();
  for (const titleNode of candidates) {
    if (!visible(titleNode)) continue;
    const title = text(titleNode).split('\n')[0].slice(0, 1000);
    if (!title || seen.has(title)) continue;
    const card = cardFor(titleNode);
    const body = text(card);
    const href = card?.querySelector("a[href*='/video/'], a[href*='/note/']")?.href || '';
    const idMatch = href.match(/\/(?:video|note)\/(\d+)/);
    const dateMatch = body.match(/(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}(?:\s+\d{1,2}:\d{2})?)/);
    const durationMatch = body.match(/(?:时长|视频时长)\s*[:：]?\s*(\d{1,2}:\d{2})/);
    let duration = null;
    if (durationMatch) {
      const parts = durationMatch[1].split(':').map(Number);
      duration = parts.length === 2 ? parts[0] * 60 + parts[1] : null;
    }
    rows.push({
      platform_post_id: idMatch?.[1] || null,
      title,
      publish_time: dateMatch ? dateMatch[1].replaceAll('/', '-') : null,
      duration,
      views: valueFor(body, '播放量') ?? valueFor(body, '播放'),
      likes: valueFor(body, '点赞'),
      comments: valueFor(body, '评论'),
      favorites: valueFor(body, '收藏'),
      shares: valueFor(body, '分享'),
    });
    seen.add(title);
  }
  return {
    rows,
    pageTitle: document.title,
    loginPrompt: /登录/.test(document.body?.innerText || '') && rows.length === 0,
  };
};
