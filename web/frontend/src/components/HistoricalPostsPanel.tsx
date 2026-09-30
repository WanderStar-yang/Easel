import { useCallback, useEffect, useRef, useState } from 'react';
import {
  confirmCreatorCenterSnapshot, confirmHistoricalImport, confirmHistoricalRepair, controlCreatorCenterSyncSession,
  createCreatorCenterSyncSession, createHistoricalPost, deleteHistoricalPost,
  fetchHistoricalPosts, getCreatorCenterSyncSession, getDouyinOpenApiStatus, getHistoricalCompleteness,
  getHistoricalSyncStatus, previewHistoricalImport, previewHistoricalRepair, updateHistoricalPost,
  listCreatorCenterSyncSessions,
} from '../lib/api';
import type {
  CreatorCenterSyncSession, DouyinOpenApiStatus, HistoricalCompleteness, HistoricalImportPreview, HistoricalRepairPreview,
  HistoricalPost, HistoricalPostInput, HistoricalSyncStatus, OperatorAccount,
} from '../lib/api';

type FormState = Record<string, string>;

const FIELD_LABELS: Record<string, string> = {
  publish_time: '发布时间', title: '标题', content_type: '内容类型', content_source: '内容来源',
  tags: '标签（逗号分隔）', note: '备注', duration: '时长（秒）', subjects: '出镜主体（逗号分隔）',
  hook_type: 'Hook 类型', views: '播放 / 浏览 / 曝光', likes: '点赞', comments: '评论',
  favorites: '收藏', shares: '分享', followers_gain: '涨粉', profile_visits: '主页访问', inquiries: '咨询',
  platform_post_id: '平台作品 ID（可选）',
};

function emptyForm(): FormState {
  return {
    publish_time: '', title: '', content_type: '', content_source: 'UNKNOWN', tags: '', note: '',
    duration: '', subjects: '', hook_type: '', views: '', likes: '', comments: '', favorites: '',
    shares: '', followers_gain: '', profile_visits: '', inquiries: '', platform_post_id: '',
  };
}

function postToForm(post: HistoricalPost): FormState {
  const form = emptyForm();
  for (const key of Object.keys(form)) {
    const value = (post as unknown as Record<string, unknown>)[key];
    if (key === 'tags' || key === 'subjects') form[key] = Array.isArray(value) ? value.join(', ') : '';
    else form[key] = value == null ? '' : String(value).slice(0, key === 'publish_time' ? 16 : undefined);
  }
  return form;
}

function formToPayload(form: FormState): HistoricalPostInput {
  const metric = (field: string) => form[field] === '' ? null : Number(form[field]);
  return {
    title: form.title.trim(), content_type: form.content_type.trim() || null,
    content_source: form.content_source as HistoricalPostInput['content_source'],
    tags: form.tags.split(/[,，;]/).map((item) => item.trim()).filter(Boolean),
    subjects: form.subjects.split(/[,，;]/).map((item) => item.trim()).filter(Boolean),
    note: form.note.trim() || null, hook_type: form.hook_type.trim() || null,
    platform_post_id: form.platform_post_id.trim() || null,
    publish_time: form.publish_time ? (form.publish_time.length === 16 ? `${form.publish_time}:00` : form.publish_time) : null,
    duration: metric('duration'), views: metric('views'), likes: metric('likes'),
    comments: metric('comments'), favorites: metric('favorites'), shares: metric('shares'),
    followers_gain: metric('followers_gain'), profile_visits: metric('profile_visits'),
    inquiries: metric('inquiries'),
  };
}

export default function HistoricalPostsPanel({ account, onClose, onRunDiagnosis, autoStartSync = false }: {
  account: OperatorAccount; onClose: () => void; onRunDiagnosis?: () => void; autoStartSync?: boolean;
}) {
  const [posts, setPosts] = useState<HistoricalPost[]>([]);
  const [postTotal, setPostTotal] = useState(0);
  const [completeness, setCompleteness] = useState<HistoricalCompleteness | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [form, setForm] = useState<FormState | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState<HistoricalImportPreview | null>(null);
  const [repairPreview, setRepairPreview] = useState<HistoricalRepairPreview | null>(null);
  const [importing, setImporting] = useState(false);
  const [importMessage, setImportMessage] = useState('');
  const [syncStatus, setSyncStatus] = useState<HistoricalSyncStatus | null>(null);
  const [openApiStatus, setOpenApiStatus] = useState<DouyinOpenApiStatus | null>(null);
  const [syncSession, setSyncSession] = useState<CreatorCenterSyncSession | null>(null);
  const [sessionBusy, setSessionBusy] = useState(false);
  const [syncWizardOpen, setSyncWizardOpen] = useState(false);
  const [otherImportOpen, setOtherImportOpen] = useState(false);
  const [syncConfirmed, setSyncConfirmed] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [history, dataQuality] = await Promise.all([
        fetchHistoricalPosts(account.id), getHistoricalCompleteness(account.id),
      ]);
      setPosts(history.items);
      setPostTotal(history.total);
      setCompleteness(dataQuality);
      if (account.platform === 'douyin') {
        const [status, apiStatus, sessions] = await Promise.all([
          getHistoricalSyncStatus(account.id), getDouyinOpenApiStatus(account.id),
          listCreatorCenterSyncSessions(account.id),
        ]);
        setSyncStatus(status);
        setOpenApiStatus(apiStatus);
        const resumable = sessions.items.find((item) => !['cancelled', 'ended'].includes(item.status));
        if (resumable) {
          setSyncSession((current) => current || resumable);
          setSyncWizardOpen(true);
          if (resumable.status === 'preview_ready' && resumable.preview) setPreview(resumable.preview);
        }
      }
    } catch {
      setError('加载历史内容失败，请重试。');
    } finally {
      setLoading(false);
    }
  }, [account.id, account.platform]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!syncSession?.session_id || syncSession.status === 'preview_ready') return;
    let stopped = false;
    const poll = async () => {
      try {
        const current = await getCreatorCenterSyncSession(account.id, syncSession.session_id);
        if (stopped) return;
        setSyncSession(current);
        if (current.status === 'preview_ready' && current.preview) {
          setPreview(current.preview);
          setImportMessage('扫描结果已送达。请检查预览后确认导入。');
        }
      } catch {
        if (!stopped) setError('同步会话已过期或失效，请重新创建同步会话。');
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1800);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [account.id, syncSession?.session_id, syncSession?.status]);

  const openCreate = () => { setEditingId(null); setForm(emptyForm()); };
  const openEdit = (post: HistoricalPost) => { setEditingId(post.id); setForm(postToForm(post)); };

  const save = async () => {
    if (!form?.title.trim()) return;
    setSaving(true);
    setError('');
    try {
      const payload = formToPayload(form);
      if (editingId) await updateHistoricalPost(account.id, editingId, payload);
      else await createHistoricalPost(account.id, payload);
      setForm(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存历史内容失败');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (post: HistoricalPost) => {
    if (!window.confirm(`删除「${post.title}」？此操作会移除这条历史记录。`)) return;
    try {
      await deleteHistoricalPost(account.id, post.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除历史内容失败');
    }
  };

  const chooseFile = async (file?: File) => {
    if (!file) return;
    setPreview(null);
    setImportMessage('');
    setError('');
    try {
      setPreview(await previewHistoricalImport(account.id, file));
    } catch (err) {
      setError(err instanceof Error ? err.message : '读取导入文件失败');
    } finally {
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const confirmImport = async () => {
    if (!preview) return;
    setImporting(true);
    setError('');
    try {
      if (preview.preview_kind === 'snapshot') {
        if (!preview.can_confirm) throw new Error('扫描快照不完整或存在错误，不能确认同步。');
        const result = await confirmCreatorCenterSnapshot(account.id, preview.preview_id);
        setImportMessage(`全量快照已对账：新增 ${result.inserted_count}，更新 ${result.updated_count}，归档重复 ${result.archived_duplicate_count}，标记平台缺失 ${result.platform_missing_count}，回填发布时间 ${result.publish_time_backfill_count}。历史数据已更新，请重新运行账号诊断。`);
        setSyncConfirmed(true);
        setSyncSession(null);
        setSyncStatus(await getHistoricalSyncStatus(account.id));
      } else {
        const result = await confirmHistoricalImport(account.id, preview.preview_id);
        setImportMessage(`已导入 ${result.imported_count} 条，跳过重复 ${result.skipped_duplicate_count} 条，错误 ${result.error_count} 行。`);
      }
      setPreview(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : '确认导入失败');
    } finally {
      setImporting(false);
    }
  };

  const inspectHistoricalRepair = async () => {
    setSessionBusy(true);
    setError('');
    try { setRepairPreview(await previewHistoricalRepair(account.id)); }
    catch (err) { setError(err instanceof Error ? err.message : '生成历史重复修复预览失败'); }
    finally { setSessionBusy(false); }
  };

  const confirmRepair = async () => {
    if (!repairPreview) return;
    setImporting(true);
    setError('');
    try {
      const result = await confirmHistoricalRepair(account.id, repairPreview.preview_id);
      setImportMessage(`已归档 ${result.archived_duplicate_count} 条重复作品，保留 ${result.canonical_count} 条规范记录，并重映射 ${result.reference_remap_count} 条引用。请重新运行账号诊断。`);
      setRepairPreview(null);
      await load();
    } catch (err) { setError(err instanceof Error ? err.message : '确认历史重复修复失败'); }
    finally { setImporting(false); }
  };

  const startCreatorSync = async () => {
    setSessionBusy(true);
    setError('');
    setImportMessage('');
    setPreview(null);
    try {
      const session = await createCreatorCenterSyncSession(account.id);
      setSyncSession(session);
      setSyncWizardOpen(true);
      setSyncConfirmed(false);
      setImportMessage('同步向导已启动。请先安装并连接浏览器辅助扩展。');
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建同步会话失败');
    } finally {
      setSessionBusy(false);
    }
  };

  const copySessionId = async () => {
    if (!syncSession?.session_id) return;
    try {
      await navigator.clipboard.writeText(syncSession.session_id);
      setImportMessage('会话码已复制。请粘贴到 Chrome 的 Easel 抖音同步扩展。');
    } catch {
      setError('浏览器未允许复制，请手动选择并复制会话码。');
    }
  };

  const refreshSyncState = async () => {
    if (!syncSession) return;
    try {
      const current = await getCreatorCenterSyncSession(account.id, syncSession.session_id);
      setSyncSession(current);
      if (current.status === 'preview_ready' && current.preview) {
        setPreview(current.preview);
        setImportMessage('扫描结果已送达。请检查预览后确认导入。');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '同步会话已过期，请重新开始。');
    }
  };

  const controlSync = async (action: 'pause' | 'resume' | 'end' | 'cancel') => {
    if (!syncSession) return;
    try {
      const updated = await controlCreatorCenterSyncSession(account.id, syncSession.session_id, action);
      setSyncSession(updated);
      if (action === 'cancel') setImportMessage('扫描已取消。已保存的页检查点仍可查看，但不能生成导入预览。');
      if (action === 'resume') setImportMessage('继续指令已保存。请打开同步扩展并点击“继续 / 恢复扫描”。');
      if (action === 'end') setImportMessage(
        updated.status === 'end_requested'
          ? '已通知扩展结束扫描；请保持扩展弹窗打开，当前页保存后会自动生成部分预览。'
          : '扫描已结束，检查点已保留。请在创作者中心的 Easel 扩展中点击“生成预览”查看已保存内容。部分预览不能确认同步。',
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新同步控制状态失败');
    }
  };

  const openCreatorCenter = () => {
    window.open('https://creator.douyin.com/creator-micro/content/manage', '_blank', 'noopener,noreferrer');
  };

  useEffect(() => {
    if (autoStartSync && isDouyin) void startCreatorSync();
    // Start a new short-lived account-bound sync session only on entry from the empty-diagnosis guide.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account.id, autoStartSync]);

  const syncStateLabels: Record<CreatorCenterSyncSession['status'], string> = {
    extension_unavailable: '未检测到扩展连接', extension_available: '扩展已连接',
    creator_tab_not_found: '未找到创作者中心标签页', not_logged_in: '等待你在网页中自行登录',
    unsupported_page: '当前不是作品管理页面', ready_to_scan: '作品管理页面就绪，可以扫描',
    scanning: '正在扫描历史作品', scan_completed: '扫描完成，等待预览', preview_ready: '同步预览已就绪',
    paused: '扫描已暂停', pause_requested: '正在保存当前页并暂停', resume_requested: '等待扩展继续扫描',
    end_requested: '正在结束扫描', ended: '已结束扫描', cancelled: '已取消', scan_failed: '扫描失败',
  };

  const isDouyin = account.platform === 'douyin';
  const extraFields = isDouyin
    ? ['duration', 'subjects', 'hook_type', 'views', 'likes', 'comments', 'favorites', 'shares', 'followers_gain']
    : ['views', 'likes', 'favorites', 'comments', 'shares', 'followers_gain', 'profile_visits', 'inquiries'];
  const editableFields = ['publish_time', 'title', 'content_type', 'content_source', ...extraFields,
    'tags', 'note', 'platform_post_id'];

  return (
    <section className="card" style={{ marginTop: 20, padding: 18 }} aria-label={`${account.name}历史内容`}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 19 }}>{account.name} · 历史内容</h2>
          <p className="page-subtitle" style={{ margin: '5px 0 0' }}>
            当前账号：{isDouyin ? '抖音宠物账号' : '小红书独立开发者账号'}。记录只归属此账号。
          </p>
        </div>
        <button className="btn btn-sm" onClick={onClose}>收起</button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 10, marginTop: 16 }}>
        <span className="badge">历史作品 {completeness?.sample_size ?? 0} 条</span>
        <span className="badge">数据完整度 {completeness?.score ?? 0}%</span>
        {isDouyin && <button className="btn btn-sm btn-primary" onClick={() => void startCreatorSync()} disabled={sessionBusy}>
          {sessionBusy ? '创建会话…' : '同步抖音数据'}
        </button>}
        {isDouyin ? (
          <button className="btn btn-sm" onClick={() => setOtherImportOpen((open) => !open)}>
            其他导入方式 {otherImportOpen ? '▲' : '▼'}
          </button>
        ) : <>
          <button className="btn btn-sm" onClick={() => fileRef.current?.click()}>导入 CSV / XLSX</button>
          <button className="btn btn-sm" onClick={openCreate}>+ 手动添加</button>
        </>}
        <input ref={fileRef} type="file" accept=".csv,.xlsx" hidden
          onChange={(event) => void chooseFile(event.target.files?.[0])} />
      </div>

      {isDouyin && otherImportOpen && (
        <div className="card" style={{ marginTop: 12, padding: 12 }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn btn-sm" onClick={() => fileRef.current?.click()}>导入 CSV / XLSX</button>
            <button className="btn btn-sm" onClick={openCreate}>手动添加</button>
          </div>
          <details style={{ marginTop: 10 }}>
            <summary style={{ cursor: 'pointer', fontSize: 13 }}>抖音官方 OpenAPI（高级选项）</summary>
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
              状态：{openApiStatus?.configured ? '已配置' : '未配置'}。{openApiStatus?.message || '正在检查配置…'}
              {openApiStatus && !openApiStatus.configured && ` 缺少：${openApiStatus.missing_configuration.join('、')}`}
              <div style={{ marginTop: 5 }}>OpenAPI 不是 V1 同步前置条件，未配置时仍可通过创作者中心同步。</div>
              <a href="https://open.douyin.com/" target="_blank" rel="noreferrer">查看抖音开放平台配置说明</a>
            </div>
          </details>
        </div>
      )}

      {isDouyin && (
        <div className="card" style={{ marginTop: 12, padding: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>抖音创作者中心同步</div>
          <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-secondary)' }}>
            每次扫描账号全部历史作品，生成 Full Snapshot；只有完整扫描并确认后才与数据库对账。
          </div>
          <div style={{ marginTop: 5, fontSize: 12, color: 'var(--text-secondary)' }}>
            上次同步：{syncStatus?.last_sync_at ? new Date(syncStatus.last_sync_at).toLocaleString() : '尚未同步'}
            {syncStatus?.last_sync_source ? ` · 来源 ${syncStatus.last_sync_source}` : ''}
            {` · 当前作品 ${postTotal} 条`}
            {syncStatus?.last_sync_counts && Object.keys(syncStatus.last_sync_counts).length > 0
              ? ` · 上次新增 ${syncStatus.last_sync_counts.inserted_count ?? 0} / 更新 ${syncStatus.last_sync_counts.updated_count ?? 0} / 重复 ${syncStatus.last_sync_counts.duplicate_count ?? 0}`
              : ''}
          </div>
          <button className="btn btn-sm" style={{ marginTop: 8 }} onClick={() => void inspectHistoricalRepair()} disabled={sessionBusy}>
            {sessionBusy ? '正在生成预览…' : '检查历史重复并生成修复预览'}
          </button>
          {syncWizardOpen && syncSession && (
            <div className="card" style={{ marginTop: 10, padding: 12 }} aria-label="抖音创作者中心同步向导">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <strong>同步向导 · {account.name}</strong>
                <span style={{ display: 'flex', flexWrap: 'wrap', gap: 6, justifyContent: 'flex-end' }}>
                  <span className={`badge ${syncSession.extension_available ? 'badge-ok' : ''}`}>
                    {syncSession.extension_available ? '扩展已连接' : '扩展不可用'}
                  </span>
                  <span className="badge">{syncStateLabels[syncSession.status]}</span>
                </span>
              </div>
              <div role="status" style={{ fontSize: 12, marginTop: 8 }}>{syncSession.message}</div>
              <ol style={{ paddingLeft: 22, fontSize: 12, lineHeight: 1.7 }}>
                <li>
                  <strong>检测扩展</strong>：如果未安装，请打开 Chrome 扩展程序页，开启“开发者模式”，选择“加载已解压的扩展程序”，载入仓库目录 <code>browser-helpers/douyin-sync/</code>。安装后在扩展弹窗粘贴下面的会话码并点击“检测当前页面并连接”。
                  {syncSession.status === 'extension_unavailable' && <div style={{ marginTop: 5 }}>需要安装 Douyin Sync 浏览器辅助扩展。浏览器网页不能直接枚举扩展；连接成功后此处会自动更新。</div>}
                </li>
                <li>
                  <strong>打开创作者中心</strong>：点击下方按钮后，请在新标签页中自行扫码或登录。系统不会自动登录或读取凭证。
                  <div><button className="btn btn-sm" onClick={openCreatorCenter}>打开抖音创作者中心</button></div>
                </li>
                <li><strong>检测页面</strong>：登录后进入作品管理 / 内容管理 / 视频列表，再从扩展弹窗点击“检测当前页面并连接”。状态会显示“可扫描”。</li>
                <li><strong>扫描全部作品并预览</strong>：在扩展弹窗点击“开始扫描历史作品”。扩展逐页确认翻页变化并保存当前全量 Snapshot 检查点；到达末页后，点击“生成预览（完成后切回 Easel 查看）”。扫描不写作品数据库。</li>
                <li><strong>确认快照同步</strong>：Easel 显示平台唯一作品、当前数据库、新增、更新、扫描重复、历史重复、平台缺失和发布时间回填，再点击“确认同步”。</li>
              </ol>
              <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                <input className="field" readOnly value={syncSession.session_id} aria-label="同步会话码" />
                <button className="btn btn-sm" onClick={() => void copySessionId()}>复制会话码</button>
                <button className="btn btn-sm" onClick={() => void refreshSyncState()}>我已安装，重新检测</button>
              </div>
              <div style={{ fontSize: 12, marginTop: 8 }}>
                已扫描 {syncSession.unique_count ?? 0}{syncSession.expected_count != null ? ` / ${syncSession.expected_count}` : ''} 条唯一作品 · 原始观测 {syncSession.raw_observation_count ?? 0} 条 · 重复 {syncSession.duplicate_count ?? 0} 条 · {syncSession.pages_scanned ?? 0} 页
                {syncSession.next_page_hint ? ` · 续扫位置：${syncSession.next_page_hint}` : ''}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                {(syncSession.status === 'scanning' || syncSession.status === 'pause_requested') && <button className="btn btn-sm" onClick={() => void controlSync('pause')}>暂停扫描</button>}
                {['paused', 'scanning', 'scan_failed', 'resume_requested'].includes(syncSession.status) && <button className="btn btn-sm" onClick={() => void controlSync('resume')}>继续 / 恢复</button>}
                {!['ended', 'cancelled', 'preview_ready'].includes(syncSession.status) && <button className="btn btn-sm" onClick={() => void controlSync('end')}>结束扫描</button>}
                {!['ended', 'cancelled', 'preview_ready'].includes(syncSession.status) && <button className="btn btn-sm" onClick={() => void controlSync('cancel')}>取消扫描</button>}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 6 }}>检查点保留 7 天；页面刷新或浏览器重启后可从同一会话恢复。</div>
            </div>
          )}
        </div>
      )}

      {completeness && (
        <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-secondary)' }}>
          完整度依据样本数量、发布时间、内容类型、播放/曝光和互动数据覆盖率计算。
          {Object.entries(completeness.coverage).map(([key, value]) => (
            <span key={key} style={{ marginLeft: 10 }}>{FIELD_LABELS[key] || key} {Math.round(value * 100)}%</span>
          ))}
        </div>
      )}
      {error && <div role="alert" style={{ color: 'var(--red)', fontSize: 13, marginTop: 12 }}>{error}</div>}
      {importMessage && <div role="status" className="card" style={{ padding: 10, marginTop: 12 }}>{importMessage}</div>}

      {preview && (
        <div className="card" style={{ marginTop: 16, padding: 14 }}>
          {preview.preview_kind === 'snapshot' ? <>
          <h3 style={{ margin: '0 0 10px' }}>{preview.snapshot_complete ? '抖音完整作品 Snapshot 预览' : '抖音已扫描内容预览（未完成）'}</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
            <span className="badge">平台唯一作品 {preview.platform_unique_count}</span>
            <span className="badge">数据库当前记录 {preview.database_current_count}</span>
            <span className="badge">新增 {preview.insert_count}</span>
            <span className="badge">更新 {preview.update_count}</span>
            <span className="badge">扫描重复 {preview.scan_duplicate_count}</span>
            <span className="badge">历史重复待合并 {preview.historical_duplicate_count}</span>
            <span className="badge">平台当前缺失 {preview.platform_missing_count}</span>
            <span className="badge">发布时间待回填 {preview.publish_time_backfill_count}</span>
            <span className="badge">错误 {preview.error_count}</span>
          </div>
          <div role="status" style={{ fontSize: 12, marginBottom: 10 }}>{preview.message}</div>
          {(preview.errors || []).map((item) => (
            <div key={item.row} style={{ color: 'var(--red)', fontSize: 12 }}>
              第 {item.row} 条「{item.title}」：{Object.values(item.errors).join('；')}
            </div>
          ))}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
            <button className="btn btn-sm" onClick={() => setPreview(null)}>取消</button>
            <button className="btn btn-sm btn-primary" onClick={() => void confirmImport()} disabled={importing || !preview.can_confirm}>
              {importing ? '对账中…' : '确认同步'}
            </button>
          </div>
          </> : <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
            {preview.raw_observation_count != null && <span className="badge">原始观测 {preview.raw_observation_count}</span>}
            {preview.unique_count != null && <span className="badge">唯一作品 {preview.unique_count}</span>}
            {preview.scan_duplicate_count != null && <span className="badge">扫描内重复 {preview.scan_duplicate_count}</span>}
            {preview.pages_scanned != null && <span className="badge">扫描页数 {preview.pages_scanned}</span>}
            <span className="badge">总行数 {preview.total_rows}</span>
            <span className="badge badge-ok">可导入 {preview.importable_count}</span>
            {preview.update_count != null && <span className="badge">将更新 {preview.update_count}</span>}
            <span className="badge">错误 {preview.error_count}</span>
            <span className="badge">重复 {preview.duplicate_count}（确认时跳过）</span>
          </div>
          {preview.missing_fields.length > 0 && (
            <div style={{ fontSize: 12, marginBottom: 10 }}>
              缺失字段：{preview.missing_fields.map((item) =>
                `${FIELD_LABELS[item.field] || item.field}${item.column_missing ? '（未提供列）' : `（${item.missing_rows} 行为空）`}`,
              ).join('、')}
            </div>
          )}
          {!!preview.ignored_columns?.length && (
            <div style={{ fontSize: 12, marginBottom: 10 }}>
              以下导出列当前不会写入历史内容：{preview.ignored_columns.join('、')}。其余已识别字段仍可正常导入。
            </div>
          )}
          <div style={{ maxHeight: 230, overflowY: 'auto', fontSize: 12 }}>
            {preview.rows.map((row) => (
              <div key={row.row} style={{ borderTop: '1px solid var(--border)', padding: '7px 0' }}>
                <strong>第 {row.row} 行 · {row.status === 'ready' ? '可导入' : row.status === 'update' ? '将更新现有作品指标' : row.status === 'duplicate' ? '重复，将跳过' : '有错误'}</strong>
                {' · '}{String(row.record.title || '（无标题）')}
                {Object.entries(row.errors).map(([field, message]) => (
                  <div key={field} style={{ color: 'var(--red)' }}>{FIELD_LABELS[field] || field}：{message}</div>
                ))}
              </div>
            ))}
            {preview.preview_truncated && <div>仅显示前 100 行预览。</div>}
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
            <button className="btn btn-sm" onClick={() => setPreview(null)}>取消</button>
            <button className="btn btn-sm btn-primary" onClick={() => void confirmImport()}
              disabled={importing || (preview.importable_count === 0 && !preview.update_count)}>
              {importing ? '导入中…' : `确认新增 ${preview.importable_count} 条${preview.update_count ? `，更新 ${preview.update_count} 条` : ''}`}
            </button>
          </div>
          </>}
        </div>
      )}

      {repairPreview && (
        <div className="card" style={{ marginTop: 16, padding: 14 }} aria-label="历史重复修复预览">
          <h3 style={{ margin: '0 0 10px' }}>历史重复修复预览 · {account.name}</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            <span className="badge">数据库当前 {repairPreview.database_current_count}</span>
            <span className="badge">重复组 {repairPreview.duplicate_groups}</span>
            <span className="badge">重复待归档 {repairPreview.duplicate_count}</span>
            <span className="badge badge-ok">修复后规范记录 {repairPreview.canonical_count_after_repair}</span>
            <span className="badge">待重映射引用 {repairPreview.reference_remap_count}</span>
          </div>
          <div style={{ maxHeight: 200, overflowY: 'auto', marginTop: 8, fontSize: 12 }}>
            {repairPreview.groups.map((group) => <div key={group.canonical_id} style={{ borderTop: '1px solid var(--border)', padding: '6px 0' }}>
              {group.title || '（无标题）'} · 归档 {group.duplicate_ids.length} 条 · 合并 {group.merged_fields.join('、') || '无额外字段'}
            </div>)}
            {repairPreview.preview_truncated && <div>仅展示前 200 个重复组。</div>}
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
            <button className="btn btn-sm" onClick={() => setRepairPreview(null)}>取消</button>
            <button className="btn btn-sm btn-primary" onClick={() => void confirmRepair()} disabled={importing || repairPreview.duplicate_count === 0}>
              {importing ? '归档中…' : `确认归档 ${repairPreview.duplicate_count} 条重复记录`}
            </button>
          </div>
        </div>
      )}

      {loading ? <div className="loading" style={{ padding: 22 }}>正在读取历史内容…</div> : posts.length === 0 ? (
        <div className="card" style={{ marginTop: 14, padding: 20, textAlign: 'center', color: 'var(--text-secondary)' }}>
          这个账号还没有历史作品。{isDouyin ? '可以从抖音创作者中心同步，也可以导入 CSV / XLSX 或手动添加。' : '可以导入 CSV / XLSX 或手动添加。'}
        </div>
      ) : (
        <div className="accounts-grid" style={{ marginTop: 14 }}>
          {posts.map((post) => (
            <article key={post.id} className="card account-card">
              <div className="account-card-head">
                <span className="account-card-name">{post.title}</span>
                <span className="badge">{post.content_source}</span>
              </div>
              <div className="account-card-note" style={{ marginTop: 7 }}>
                {post.publish_time?.slice(0, 10) || (post.publish_time_raw ? `${post.publish_time_raw}（未标准化）` : '未填写发布时间')}{post.content_type ? ` · ${post.content_type}` : ''}
                {post.source_presence === 'MISSING' && <span className="badge" style={{ marginLeft: 6 }}>平台当前未见</span>}
              </div>
              <div style={{ fontSize: 12, marginTop: 8, lineHeight: 1.6 }}>
                播放/曝光 {post.views ?? '—'} · 赞 {post.likes ?? '—'} · 藏 {post.favorites ?? '—'} · 评 {post.comments ?? '—'}
                {post.note && <div style={{ marginTop: 5 }}>{post.note}</div>}
              </div>
              <div style={{ display: 'flex', gap: 7, marginTop: 'auto', paddingTop: 10 }}>
                <button className="btn btn-sm" onClick={() => openEdit(post)}>编辑</button>
                <button className="btn btn-sm btn-ghost" onClick={() => void remove(post)}>删除</button>
              </div>
            </article>
          ))}
        </div>
      )}

      {syncConfirmed && !preview && onRunDiagnosis && (
        <button className="btn btn-sm btn-primary" style={{ marginTop: 12 }} onClick={onRunDiagnosis} disabled={postTotal === 0}>
          开始首次账号诊断
        </button>
      )}

      {form && (
        <div className="overlay" onClick={() => setForm(null)}>
          <div className="modal" style={{ width: 620, maxWidth: '100%', maxHeight: '90vh', overflowY: 'auto' }}
            onClick={(event) => event.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0 }}>{editingId ? '编辑历史内容' : '人工新增历史内容'}</h3>
              <button className="icon-btn" onClick={() => setForm(null)}>×</button>
            </div>
            <p className="page-subtitle" style={{ margin: '5px 0 14px' }}>归属：{account.name}（{isDouyin ? '抖音' : '小红书'}）</p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '0 12px' }}>
              {editableFields.map((field) => (
                <label key={field} className="field-label" style={field === 'note' ? { gridColumn: '1 / -1' } : undefined}>
                  {FIELD_LABELS[field]}{field === 'title' ? ' *' : ''}
                  {field === 'content_source' ? (
                    <select className="field" value={form[field]} onChange={(event) => setForm({ ...form, [field]: event.target.value })}>
                      {['REAL', 'AI', 'MIXED', 'UNKNOWN'].map((value) => <option key={value}>{value}</option>)}
                    </select>
                  ) : field === 'note' ? (
                    <textarea className="field" value={form[field]} rows={3}
                      onChange={(event) => setForm({ ...form, [field]: event.target.value })} />
                  ) : (
                    <input className="field" type={field === 'publish_time' ? 'datetime-local' : field === 'title' || ['content_type', 'tags', 'subjects', 'hook_type', 'platform_post_id'].includes(field) ? 'text' : 'number'}
                      min={['followers_gain'].includes(field) ? undefined : 0}
                      step={field === 'duration' ? '0.1' : field === 'title' || ['content_type', 'tags', 'subjects', 'hook_type', 'platform_post_id'].includes(field) ? undefined : '1'}
                      value={form[field]} required={field === 'title'}
                      onChange={(event) => setForm({ ...form, [field]: event.target.value })} />
                  )}
                </label>
              ))}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
              <button className="btn btn-sm" onClick={() => setForm(null)}>取消</button>
              <button className="btn btn-sm btn-primary" onClick={() => void save()} disabled={saving || !form.title.trim()}>
                {saving ? '保存中…' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
