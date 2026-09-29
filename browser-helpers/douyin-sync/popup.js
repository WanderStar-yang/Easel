const sessionInput = document.querySelector('#session');
const baseInput = document.querySelector('#base');
const statusBox = document.querySelector('#status');
const detectButton = document.querySelector('#detect');
const scanButton = document.querySelector('#scan');
const submitButton = document.querySelector('#submit');
const ACCOUNT_ID = 'douyin-pet';

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

function endpoint(session, action) {
  const base = baseInput.value.trim().replace(/\/$/, '');
  return `${base}/api/operator/accounts/${ACCOUNT_ID}/posts/sync/sessions/${encodeURIComponent(session)}/${action}`;
}

async function report(status, message, sourceUrl = '') {
  const session = sessionInput.value.trim();
  if (!session) return;
  const response = await fetch(endpoint(session, 'extension-state'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, message, source_url: sourceUrl }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Easel 同步会话响应 ${response.status}`);
  }
  return response.json();
}

async function inspectActiveTab() {
  await report('extension_available', 'Easel 抖音同步扩展已连接');
  const tab = await activeTab();
  if (!tab?.id || !tab.url) {
    await report('creator_tab_not_found', '没有找到抖音创作者中心标签页');
    throw new Error('没有找到可访问的标签页。请先点击 Easel 中的“打开抖音创作者中心”。');
  }
  let url;
  try { url = new URL(tab.url); } catch { url = null; }
  if (url?.hostname !== 'creator.douyin.com') {
    await report('creator_tab_not_found', '当前标签页不是抖音创作者中心');
    throw new Error('当前标签页不是抖音创作者中心。请切换到创作者中心标签页。');
  }
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['scanner.js'] });
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id }, func: () => window.__easelDouyinInspect(),
  });
  if (result.loginPrompt) {
    await report('not_logged_in', '创作者中心尚未登录，请在网页中自行扫码或登录', tab.url);
    return { tab, result };
  }
  if (!result.supportedPage) {
    await report('unsupported_page', '已打开创作者中心，请进入作品管理、内容管理或视频列表', tab.url);
    return { tab, result };
  }
  await report('ready_to_scan', '已连接创作者中心作品管理页，可以开始扫描', tab.url);
  return { tab, result };
}

async function detect() {
  detectButton.disabled = true;
  try {
    const { result } = await inspectActiveTab();
    statusBox.textContent = result.loginPrompt
      ? '创作者中心未登录。请在此网页中自行扫码或登录，然后重新检测当前页面。'
      : result.supportedPage
        ? '扩展已连接，作品管理页面就绪。可开始扫描历史作品。'
        : '扩展已连接，但当前页面不支持扫描。请进入作品管理 / 内容管理 / 视频列表后重新检测。';
  } catch (error) {
    statusBox.textContent = error instanceof Error ? error.message : String(error);
  } finally {
    detectButton.disabled = false;
  }
}

async function loadDraft() {
  const saved = await chrome.storage.session.get(['session', 'base', 'records']);
  if (saved.session) sessionInput.value = saved.session;
  if (saved.base) baseInput.value = saved.base;
  const count = Array.isArray(saved.records) ? saved.records.length : 0;
  statusBox.textContent = `当前累计 ${count} 条。粘贴 Easel 会话码后点击“检测当前页面并连接”。`;
}

detectButton.addEventListener('click', async () => {
  await chrome.storage.session.set({ session: sessionInput.value.trim(), base: baseInput.value.trim() });
  await detect();
});

scanButton.addEventListener('click', async () => {
  scanButton.disabled = true;
  try {
    const { tab, result } = await inspectActiveTab();
    if (result.loginPrompt) throw new Error('请先在创作者中心自行登录，再重新检测。');
    if (!result.supportedPage) throw new Error('请先进入作品管理 / 内容管理 / 视频列表。');
    await report('scanning', '正在扫描可见作品并辅助滚动/翻页', tab.url);
    const [{ result: scanResult }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: async () => {
        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
        const rows = [];
        const collect = () => {
          for (const row of window.__easelDouyinScanVisible().rows) {
            const key = row.platform_post_id || `${row.title}|${row.publish_time}`;
            const old = rows.find((item) => (item.platform_post_id || `${item.title}|${item.publish_time}`) === key);
            if (old) Object.assign(old, Object.fromEntries(Object.entries(row).filter(([, value]) => value != null)));
            else rows.push(row);
          }
        };
        const scanPageWithScroll = async () => {
          const scrollTarget = [...document.querySelectorAll('*')]
            .filter((element) => element.scrollHeight > element.clientHeight + 80 && element.clientHeight > 100)
            .sort((a, b) => b.clientHeight - a.clientHeight)[0] || document.scrollingElement;
          let stalled = 0;
          for (let step = 0; step < 30 && stalled < 2; step += 1) {
            collect();
            const before = scrollTarget.scrollTop;
            const height = scrollTarget.scrollHeight;
            scrollTarget.scrollTop = Math.min(before + Math.max(400, scrollTarget.clientHeight * 0.8), height);
            window.scrollBy(0, Math.max(300, window.innerHeight * 0.75));
            await sleep(650);
            stalled = scrollTarget.scrollTop === before && scrollTarget.scrollHeight === height ? stalled + 1 : 0;
          }
          collect();
        };
        const fingerprint = () => {
          const first = window.__easelDouyinScanVisible().rows[0];
          return first ? (first.platform_post_id || `${first.title}|${first.publish_time}`) : '';
        };
        let autoAdvanced = false;
        let pagesScanned = 0;
        for (let pageNumber = 0; pageNumber < 10; pageNumber += 1) {
          await scanPageWithScroll();
          pagesScanned += 1;
          const beforePage = fingerprint();
          const next = [...document.querySelectorAll('button,[role="button"],a')]
            .find((node) => /^(下一页|下页|next)$/i.test((node.innerText || node.getAttribute('aria-label') || node.title || '').trim())
              && !node.disabled && node.getAttribute('aria-disabled') !== 'true'
              && node.getClientRects().length);
          if (!next || !rows.length) break;
          next.click();
          autoAdvanced = true;
          await sleep(1200);
          if (fingerprint() === beforePage) break;
        }
        return { rows, autoAdvanced, pagesScanned };
      },
    });
    if (!scanResult.rows.length) throw new Error('当前页面没有识别到作品。请确认作品列表已加载，或手动滚动/切换页后重试。');
    const saved = await chrome.storage.session.get('records');
    const prior = Array.isArray(saved.records) ? saved.records : [];
    const merged = EaselDouyinSync.mergeRows(prior, scanResult.rows);
    await chrome.storage.session.set({ session: sessionInput.value.trim(), base: baseInput.value.trim(), records: merged });
    await report('scan_completed', `本次识别 ${scanResult.rows.length} 条，扩展累计 ${merged.length} 条`, tab.url);
    statusBox.textContent = `本次扫描 ${scanResult.rows.length} 条，累计 ${merged.length} 条，扫描 ${scanResult.pagesScanned} 页。${scanResult.autoAdvanced ? '已辅助翻页。' : '如还有更早作品，请手动进入下一页后再次扫描。'}`;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    await report('scan_failed', message).catch(() => {});
    statusBox.textContent = message;
  } finally {
    scanButton.disabled = false;
  }
});

submitButton.addEventListener('click', async () => {
  submitButton.disabled = true;
  try {
    const session = sessionInput.value.trim();
    const base = baseInput.value.trim().replace(/\/$/, '');
    if (!session) throw new Error('请粘贴 Easel 同步会话码。');
    const { tab, result } = await inspectActiveTab();
    if (result.loginPrompt) throw new Error('请先在创作者中心自行登录。');
    if (!result.supportedPage) throw new Error('请在作品管理页面生成预览。');
    const saved = await chrome.storage.session.get('records');
    const rows = Array.isArray(saved.records) ? saved.records : [];
    if (!rows.length) throw new Error('还没有扫描作品。请先点击“开始扫描历史作品”。');
    const response = await fetch(`${base}/api/operator/accounts/${ACCOUNT_ID}/posts/sync/sessions/${encodeURIComponent(session)}/preview`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_url: tab.url, records: rows }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `Easel 请求失败：${response.status}`);
    await chrome.storage.session.remove('records');
    statusBox.textContent = `预览已送到 Easel：扫描 ${payload.preview?.scanned_count ?? rows.length} 条，新增 ${payload.preview?.importable_count ?? 0} 条，更新 ${payload.preview?.update_count ?? 0} 条，重复 ${payload.preview?.duplicate_count ?? 0} 条，错误 ${payload.preview?.error_count ?? 0} 条。请回 Easel 检查并确认。`;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    await report('scan_failed', message).catch(() => {});
    statusBox.textContent = message;
  } finally {
    submitButton.disabled = false;
  }
});

void loadDraft();
