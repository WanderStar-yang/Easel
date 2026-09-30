const sessionInput = document.querySelector('#session');
const baseInput = document.querySelector('#base');
const statusBox = document.querySelector('#status');
const detectButton = document.querySelector('#detect');
const scanButton = document.querySelector('#scan');
const pauseButton = document.querySelector('#pause');
const resumeButton = document.querySelector('#resume');
const endButton = document.querySelector('#end');
const cancelButton = document.querySelector('#cancel');
const submitButton = document.querySelector('#submit');
const ACCOUNT_ID = 'douyin-pet';
const STORAGE_KEY = 'easelDouyinSync';
const CREATOR_URL = 'https://creator.douyin.com/creator-micro/content/manage';
let scanLoopRunning = false;
let endThenPreview = false;

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

function endpoint(session, action = '') {
  const base = baseInput.value.trim().replace(/\/$/, '');
  const path = `${base}/api/operator/accounts/${ACCOUNT_ID}/posts/sync/sessions/${encodeURIComponent(session)}`;
  return action ? `${path}/${action}` : path;
}

async function requestSession() {
  const response = await fetch(endpoint(sessionInput.value.trim()));
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Easel 同步会话响应 ${response.status}`);
  return payload;
}

async function control(action) {
  const session = sessionInput.value.trim();
  if (!session) throw new Error('请先粘贴 Easel 同步会话码。');
  const response = await fetch(endpoint(session, 'control'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Easel 同步会话响应 ${response.status}`);
  return payload;
}

async function report(status, message, sourceUrl = '') {
  const session = sessionInput.value.trim();
  if (!session) return;
  const response = await fetch(endpoint(session, 'extension-state'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, message, source_url: sourceUrl }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Easel 同步会话响应 ${response.status}`);
  return payload;
}

async function inspectActiveTab({ reportState = true } = {}) {
  if (reportState) await report('extension_available', 'Easel 抖音同步扩展已连接');
  const tab = await activeTab();
  if (!tab?.id || !tab.url) {
    if (reportState) await report('creator_tab_not_found', '没有找到抖音创作者中心标签页');
    throw new Error('没有找到可访问的标签页。请切换到抖音创作者中心。');
  }
  let url;
  try { url = new URL(tab.url); } catch { url = null; }
  if (url?.hostname !== 'creator.douyin.com') {
    if (reportState) await report('creator_tab_not_found', '当前标签页不是抖音创作者中心');
    throw new Error('当前标签页不是抖音创作者中心。请切换到创作者中心标签页。');
  }
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['scanner.js'] });
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id }, func: () => window.__easelDouyinInspect(),
  });
  if (result.loginPrompt) {
    if (reportState) await report('not_logged_in', '创作者中心尚未登录，请在网页中自行扫码或登录', tab.url);
    return { tab, result };
  }
  if (!result.supportedPage) {
    if (reportState) await report('unsupported_page', '请进入作品管理、内容管理或视频列表', tab.url);
    return { tab, result };
  }
  if (reportState) await report('ready_to_scan', '已连接创作者中心作品管理页，可以开始扫描', tab.url);
  return { tab, result };
}

async function detect() {
  detectButton.disabled = true;
  try {
    const { result } = await inspectActiveTab();
    statusBox.textContent = result.loginPrompt
      ? '创作者中心未登录。请在此网页中自行扫码或登录，然后重新检测。'
      : result.supportedPage ? '扩展已连接，作品管理页面就绪。' : '请进入作品管理 / 内容管理 / 视频列表后重新检测。';
  } catch (error) {
    statusBox.textContent = error instanceof Error ? error.message : String(error);
  } finally {
    detectButton.disabled = false;
  }
}

async function scanCurrentPage(tab) {
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const scan = window.__easelDouyinScanVisible;
      const scrollTarget = [...document.querySelectorAll('*')]
        .filter((element) => element.scrollHeight > element.clientHeight + 80 && element.clientHeight > 100)
        .sort((a, b) => b.clientHeight - a.clientHeight)[0] || document.scrollingElement;
      let stalled = 0;
      for (let step = 0; step < 80 && stalled < 3; step += 1) {
        scrollTarget.scrollTop = Math.min(scrollTarget.scrollTop + Math.max(450, scrollTarget.clientHeight * 0.75), scrollTarget.scrollHeight);
        window.scrollBy(0, Math.max(300, window.innerHeight * 0.7));
        await sleep(500);
        const atBottom = scrollTarget.scrollTop + scrollTarget.clientHeight >= scrollTarget.scrollHeight - 4;
        stalled = atBottom ? stalled + 1 : 0;
      }
      await sleep(800);
      return scan();
    },
  });
  return result;
}

async function advancePage(tab, priorFingerprint) {
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: async (oldFingerprint) => {
      const nodes = [...document.querySelectorAll('button,[role="button"],a,[aria-label],[title]')]
        .filter((node) => node.getClientRects().length);
      const label = (node) => `${node.innerText || node.textContent || ''} ${node.getAttribute('aria-label') || ''} ${node.title || ''}`.trim();
      const next = nodes.find((node) => /下一页|下页|后页|next/i.test(label(node))
        && node.getAttribute('aria-disabled') !== 'true' && !node.disabled);
      if (!next) return { moved: false, reason: '当前页没有可识别的下一页按钮' };
      next.click();
      const deadline = Date.now() + 15000;
      while (Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 500));
        if (!window.__easelDouyinScanVisible) continue;
        const current = window.__easelDouyinScanVisible().fingerprint;
        if (current && current !== oldFingerprint) return { moved: true, reason: '已检测到作品列表变化' };
      }
      return { moved: false, reason: '等待 15 秒仍未确认列表变化' };
    }, args: [priorFingerprint],
  });
  return result;
}

async function runScan() {
  if (scanLoopRunning) return;
  scanLoopRunning = true;
  scanButton.disabled = true;
  try {
    const { tab, result: page } = await inspectActiveTab();
    if (page.loginPrompt) throw new Error('请先在创作者中心自行登录，再重新检测。');
    if (!page.supportedPage) throw new Error('请先进入作品管理 / 内容管理 / 视频列表。');
    await report('scanning', '正在扫描账号全部历史作品并保存 Snapshot 检查点', tab.url);
    for (let pageCount = 0; pageCount < 500; pageCount += 1) {
      const session = await requestSession();
      if (session.status === 'cancelled') break;
      if (session.status === 'pause_requested') {
        await report('paused', '已保存当前进度，可继续扫描', tab.url);
        break;
      }
      if (session.status === 'end_requested') {
        endThenPreview = true;
        await report('ended', '已按要求结束扫描，可为已保存作品生成预览', tab.url);
        break;
      }
      const current = await scanCurrentPage(tab);
      if (!current.rows.length && !session.unique_count) throw new Error('当前页面没有识别到作品，请确认作品列表已加载。');
      const checkpoint = await fetch(endpoint(sessionInput.value.trim(), 'checkpoint'), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_url: tab.url, page_fingerprint: current.fingerprint,
          rows: current.rows, has_next: current.hasNext, expected_count: current.expectedCount,
          next_page_hint: current.hasNext ? (current.pageNumber ? `第 ${current.pageNumber} 页之后` : '手动进入下一页') : '' }),
      });
      const saved = await checkpoint.json();
      if (!checkpoint.ok) throw new Error(saved.detail || `保存扫描检查点失败：${checkpoint.status}`);
      statusBox.textContent = `第 ${saved.pages_scanned} 页已保存：唯一 ${saved.unique_count} / 原始 ${saved.raw_observation_count} / 重复 ${saved.duplicate_count}。`;
      if (saved.status === 'paused') statusBox.textContent = saved.message;
      if (saved.status === 'ended') endThenPreview = true;
      if (['paused', 'ended', 'cancelled'].includes(saved.status)) break;
      if (!current.hasNext) {
        await report('scan_completed', '已确认到达作品列表末页', tab.url);
        statusBox.textContent += ' 已到末页。可返回 Easel 生成预览。';
        break;
      }
      if (!current.nextLabel) {
        await report('paused', '未识别到下一页控件，当前页已保存；请手动翻页后继续', tab.url);
        statusBox.textContent += ' 未识别到下一页控件，当前页已保存；手动翻页后点“继续 / 恢复扫描”。';
        break;
      }
      const moved = await advancePage(tab, current.fingerprint);
      if (!moved.moved) {
        await report('paused', `${moved.reason}；已保存当前页，等待手动翻页后续扫`, tab.url);
        statusBox.textContent += ` ${moved.reason}；检查点已保留，手动翻页后可继续。`;
        break;
      }
      // Keep a pending end request intact while waiting for the next checkpoint.
      if (pageCount === 499) {
        await report('paused', '本轮达到 500 页保护上限；全部检查点已保存，可重新继续', tab.url);
        statusBox.textContent += ' 本轮达到 500 页保护上限，检查点已保存。';
      }
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    await report('scan_failed', message).catch(() => {});
    statusBox.textContent = message;
  } finally {
    scanLoopRunning = false;
    scanButton.disabled = false;
    await loadDraft();
    if (endThenPreview) {
      endThenPreview = false;
      try {
        const state = await requestSession();
        if (state.status !== 'scan_completed' && state.status !== 'ended') {
          await report('ended', '扫描已停止；可预览已保存的作品', state.source_url || '');
        }
        await submitPreview();
      } catch (error) {
        statusBox.textContent = error instanceof Error ? error.message : String(error);
      } finally {
        submitButton.disabled = false;
      }
    }
  }
}

async function submitPreview() {
  submitButton.disabled = true;
  try {
    const session = sessionInput.value.trim();
    if (!session) throw new Error('请粘贴 Easel 同步会话码。');
    // Previewing must not overwrite the scan's terminal status with ready_to_scan.
    const { tab, result } = await inspectActiveTab({ reportState: false });
    if (result.loginPrompt) throw new Error('请先在创作者中心自行登录。');
    if (!result.supportedPage) throw new Error('请在作品管理页面生成预览。');
    let state = await requestSession();
    if (state.status === 'cancelled') throw new Error('此同步会话已取消，请在 Easel 新建会话。');
    if (state.status === 'end_requested') {
      if (scanLoopRunning) {
        endThenPreview = true;
        statusBox.textContent = '正在等当前页保存并结束扫描；结束后会自动生成预览…';
        return;
      } else {
        // The popup may have been closed while the end request was pending.
        // In this popup there is no worker left to acknowledge it, so close the
        // session against its last saved checkpoint before generating preview.
        state = await report('ended', '扫描已停止；正在为已保存作品生成预览', state.source_url || '');
      }
    }
    if (!['scan_completed', 'ended'].includes(state.status)) {
      throw new Error('扫描仍在运行。点击“结束扫描并生成预览”后等待完成；无需再点此按钮。');
    }
    const response = await fetch(endpoint(session, 'preview'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_url: tab.url, records: [] }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `Easel 请求失败：${response.status}`);
    const complete = Boolean(payload.preview?.snapshot_complete);
    statusBox.textContent = `${complete ? '完整 Snapshot 预览' : '已扫描内容预览'}已送到 Easel：平台唯一 ${payload.preview?.platform_unique_count ?? state.unique_count ?? 0} 条，原始 ${payload.preview?.raw_observation_count ?? state.raw_observation_count ?? 0} 条，扫描重复 ${payload.preview?.scan_duplicate_count ?? state.duplicate_count ?? 0} 条。${complete ? '请回 Easel 检查对账结果。' : '这是未完成扫描的只读预览，不能确认同步。'}`;
  } catch (error) {
    statusBox.textContent = error instanceof Error ? error.message : String(error);
  } finally {
    submitButton.disabled = false;
  }
}

async function loadDraft() {
  const saved = await chrome.storage.local.get([STORAGE_KEY, 'base']);
  const draft = saved[STORAGE_KEY] || {};
  if (draft.session) sessionInput.value = draft.session;
  if (saved.base) baseInput.value = saved.base;
  if (draft.session) {
    try {
      const session = await requestSession();
      statusBox.textContent = `会话已恢复：唯一 ${session.unique_count} / 原始 ${session.raw_observation_count} / 重复 ${session.duplicate_count}，已扫 ${session.pages_scanned} 页。当前状态：${session.status}。`;
      return;
    } catch { /* An expired session should still leave the entered code visible for diagnosis. */ }
  }
  statusBox.textContent = '粘贴 Easel 会话码并连接。扫描检查点保存在 Easel，可在浏览器重启后继续。';
}

detectButton.addEventListener('click', async () => {
  await chrome.storage.local.set({ [STORAGE_KEY]: { session: sessionInput.value.trim() }, base: baseInput.value.trim() });
  await detect();
});
scanButton.addEventListener('click', () => void runScan());
submitButton.addEventListener('click', () => void submitPreview());
pauseButton.addEventListener('click', async () => { try { await control('pause'); statusBox.textContent = '已请求暂停；正在保存当前页。'; } catch (error) { statusBox.textContent = error.message; } });
resumeButton.addEventListener('click', async () => { try { await control('resume'); statusBox.textContent = '会话已恢复；正在从当前创作者中心页面续扫。'; void runScan(); } catch (error) { statusBox.textContent = error.message; } });
endButton.addEventListener('click', async () => {
  endButton.disabled = true;
  try {
    const state = await control('end');
    if (scanLoopRunning) {
      endThenPreview = true;
      submitButton.disabled = true;
      statusBox.textContent = '正在结束：当前页保存后会自动生成预览。请稍候，无需再点“生成预览”。';
    } else {
      if (state.status !== 'scan_completed' && state.status !== 'ended') {
        await report('ended', '扫描已停止；正在为已保存作品生成预览', state.source_url || '');
      }
      statusBox.textContent = '扫描已停止，正在生成预览…生成后请切回 Easel 查看。';
      await submitPreview();
    }
  } catch (error) {
    statusBox.textContent = error instanceof Error ? error.message : String(error);
  } finally {
    endButton.disabled = false;
  }
});
cancelButton.addEventListener('click', async () => { try { await control('cancel'); statusBox.textContent = '扫描已取消。'; } catch (error) { statusBox.textContent = error.message; } });
sessionInput.addEventListener('change', async () => {
  await chrome.storage.local.set({ [STORAGE_KEY]: { session: sessionInput.value.trim() }, base: baseInput.value.trim() });
});
void loadDraft();
