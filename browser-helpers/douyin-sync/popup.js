const sessionInput = document.querySelector('#session');
const baseInput = document.querySelector('#base');
const statusBox = document.querySelector('#status');
const scanButton = document.querySelector('#scan');
const submitButton = document.querySelector('#submit');

async function pageRecords() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url || new URL(tab.url).hostname !== 'creator.douyin.com') {
    throw new Error('请先在当前标签页打开 https://creator.douyin.com 并登录。');
  }
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['scanner.js'] });
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id }, func: () => window.__easelDouyinScanVisible(),
  });
  return { tab, result };
}

async function loadDraft() {
  const saved = await chrome.storage.session.get(['session', 'base', 'records']);
  if (saved.session) sessionInput.value = saved.session;
  if (saved.base) baseInput.value = saved.base;
  const count = Array.isArray(saved.records) ? saved.records.length : 0;
  statusBox.textContent = `已累计 ${count} 条。打开创作者中心某一页后可扫描；翻页/滚动后重复扫描。`;
}

scanButton.addEventListener('click', async () => {
  scanButton.disabled = true;
  try {
    const { result } = await pageRecords();
    if (result.loginPrompt) throw new Error('当前页面像是登录页，登录后再扫描作品管理页面。');
    const saved = await chrome.storage.session.get('records');
    const rows = Array.isArray(saved.records) ? saved.records : [];
    const merged = EaselDouyinSync.mergeRows(rows, result.rows);
    await chrome.storage.session.set({ session: sessionInput.value.trim(), base: baseInput.value.trim(), records: merged });
    statusBox.textContent = `本页识别 ${result.rows.length} 条，累计 ${merged.length} 条。未离开抖音页面，也未读取登录凭据。`;
  } catch (error) {
    statusBox.textContent = error instanceof Error ? error.message : String(error);
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
    const { tab, result } = await pageRecords();
    const saved = await chrome.storage.session.get('records');
    const rows = Array.isArray(saved.records) ? saved.records : [];
    if (!rows.length) throw new Error('还没有扫描作品。请先点击“扫描当前页并累计”。');
    const response = await fetch(`${base}/api/operator/accounts/douyin-pet/posts/sync/sessions/${encodeURIComponent(session)}/preview`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_url: tab.url, records: rows }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `Easel 请求失败：${response.status}`);
    await chrome.storage.session.remove('records');
    statusBox.textContent = `预览已送到 Easel：扫描 ${payload.preview?.scanned_count ?? result.rows.length} 条，可新增 ${payload.preview?.importable_count ?? 0} 条，可更新 ${payload.preview?.update_count ?? 0} 条，重复 ${payload.preview?.duplicate_count ?? 0} 条，错误 ${payload.preview?.error_count ?? 0} 条。请回 Easel 审阅并确认。`;
  } catch (error) {
    statusBox.textContent = error instanceof Error ? error.message : String(error);
  } finally {
    submitButton.disabled = false;
  }
});

void loadDraft();
