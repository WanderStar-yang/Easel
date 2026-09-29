import { useCallback, useEffect, useRef, useState } from 'react';
import {
  confirmHistoricalImport, createCreatorCenterSyncSession, createHistoricalPost, deleteHistoricalPost,
  fetchHistoricalPosts, getCreatorCenterSyncSession, getDouyinOpenApiStatus, getHistoricalCompleteness,
  getHistoricalSyncStatus, previewHistoricalImport, updateHistoricalPost,
} from '../lib/api';
import type {
  CreatorCenterSyncSession, DouyinOpenApiStatus, HistoricalCompleteness, HistoricalImportPreview,
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

export default function HistoricalPostsPanel({ account, onClose, onRunDiagnosis }: {
  account: OperatorAccount; onClose: () => void; onRunDiagnosis?: () => void;
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
  const [importing, setImporting] = useState(false);
  const [importMessage, setImportMessage] = useState('');
  const [syncStatus, setSyncStatus] = useState<HistoricalSyncStatus | null>(null);
  const [openApiStatus, setOpenApiStatus] = useState<DouyinOpenApiStatus | null>(null);
  const [syncSession, setSyncSession] = useState<CreatorCenterSyncSession | null>(null);
  const [sessionBusy, setSessionBusy] = useState(false);
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
        const [status, apiStatus] = await Promise.all([
          getHistoricalSyncStatus(account.id), getDouyinOpenApiStatus(account.id),
        ]);
        setSyncStatus(status);
        setOpenApiStatus(apiStatus);
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
        if (current.status === 'preview_ready' && current.preview) {
          setPreview(current.preview);
          setSyncSession(current);
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
      const result = await confirmHistoricalImport(account.id, preview.preview_id);
      if (result.data_source === 'DOUYIN_CREATOR_CENTER') {
        setImportMessage(`历史数据已同步：扫描 ${result.scanned_count} 条，新增 ${result.imported_count} 条，更新 ${result.updated_count} 条，重复 ${result.skipped_duplicate_count} 条，错误 ${result.error_count} 条。诊断不会自动运行。`);
        setSyncSession(null);
        setSyncStatus(await getHistoricalSyncStatus(account.id));
      } else {
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

  const startCreatorSync = async () => {
    setSessionBusy(true);
    setError('');
    setImportMessage('');
    setPreview(null);
    try {
      const session = await createCreatorCenterSyncSession(account.id);
      setSyncSession(session);
      setImportMessage('同步会话已创建。请打开抖音创作者中心、手动登录，再从扩展扫描。');
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
      setImportMessage('会话码已复制。请粘贴到 Easel 抖音同步扩展。');
    } catch {
      setError('浏览器未允许复制，请手动选择并复制会话码。');
    }
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
          {sessionBusy ? '创建会话…' : '从抖音同步'}
        </button>}
        <button className="btn btn-sm" onClick={() => fileRef.current?.click()}>导入 CSV / XLSX</button>
        <button className="btn btn-sm" onClick={openCreate}>+ 手动添加</button>
        <input ref={fileRef} type="file" accept=".csv,.xlsx" hidden
          onChange={(event) => void chooseFile(event.target.files?.[0])} />
      </div>

      {isDouyin && (
        <div className="card" style={{ marginTop: 12, padding: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>抖音历史同步</div>
          <div style={{ marginTop: 5, fontSize: 12, color: 'var(--text-secondary)' }}>
            {openApiStatus?.message || '正在检查官方接口配置…'}
            {openApiStatus && !openApiStatus.configured && <span>（缺少：{openApiStatus.missing_configuration.join('、')}；权限需另在开放平台确认）</span>}
          </div>
          <a href="https://open.douyin.com/" target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>
            抖音开放平台授权与权限申请
          </a>
          <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
            上次同步：{syncStatus?.last_sync_at ? new Date(syncStatus.last_sync_at).toLocaleString() : '尚未同步'}
            {syncStatus?.last_sync_source ? ` · 来源 ${syncStatus.last_sync_source}` : ''}
            {` · 当前作品 ${postTotal} 条`}
            {syncStatus?.last_sync_counts && Object.keys(syncStatus.last_sync_counts).length > 0
              ? ` · 上次新增 ${syncStatus.last_sync_counts.inserted_count ?? 0} / 更新 ${syncStatus.last_sync_counts.updated_count ?? 0} / 重复 ${syncStatus.last_sync_counts.duplicate_count ?? 0}`
              : ''}
          </div>
          {syncSession && (
            <div style={{ marginTop: 10, fontSize: 12 }}>
              <div>1. 打开抖音创作者中心并手动登录，进入作品管理页。</div>
              <a href="https://creator.douyin.com/creator-micro/content/manage" target="_blank" rel="noreferrer">打开创作者中心作品管理</a>
              <div style={{ marginTop: 5 }}>2. 在 Chrome 加载仓库目录 <code>browser-helpers/douyin-sync</code> 内的未打包扩展。</div>
              <div>3. 点扩展图标，粘贴会话码；翻页或滚动后继续扫描，最后生成预览。</div>
              <div>会话有效期 15 分钟，等待扩展提交扫描结果…</div>
              <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                <input className="field" readOnly value={syncSession.session_id} aria-label="同步会话码" />
                <button className="btn btn-sm" onClick={() => void copySessionId()}>复制会话码</button>
              </div>
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
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
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
                {post.publish_time?.slice(0, 10) || '未填写发布时间'}{post.content_type ? ` · ${post.content_type}` : ''}
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

      {syncStatus?.last_sync_at && !preview && onRunDiagnosis && (
        <button className="btn btn-sm btn-primary" style={{ marginTop: 12 }} onClick={onRunDiagnosis}>
          重新运行首次诊断
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
