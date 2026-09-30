import { useCallback, useEffect, useRef, useState } from 'react';
import {
  confirmHistoricalImport, confirmHistoricalRepair, confirmOfficialExportSnapshot,
  createHistoricalPost, deleteHistoricalPost, fetchHistoricalPosts, getHistoricalCompleteness,
  previewHistoricalImport, previewHistoricalRepair, updateHistoricalPost,
} from '../lib/api';
import type {
  HistoricalClassificationRow, HistoricalCompleteness, HistoricalImportPreview, HistoricalRepairPreview,
  HistoricalPost, HistoricalPostInput, OperatorAccount,
} from '../lib/api';
import HistoricalClassificationPanel from './HistoricalClassificationPanel';

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

export default function HistoricalPostsPanel({ account, onClose, onRunDiagnosis, onOpenSettings }: {
  account: OperatorAccount; onClose: () => void; onRunDiagnosis?: () => void; onOpenSettings: () => void;
}) {
  const [posts, setPosts] = useState<HistoricalPost[]>([]);
  const [completeness, setCompleteness] = useState<HistoricalCompleteness | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [form, setForm] = useState<FormState | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState<HistoricalImportPreview | null>(null);
  const [repairPreview, setRepairPreview] = useState<HistoricalRepairPreview | null>(null);
  const [manualRepairGroups, setManualRepairGroups] = useState<string[]>([]);
  const [importing, setImporting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [importMessage, setImportMessage] = useState('');
  const [showOtherImport, setShowOtherImport] = useState(false);
  const [diagnosisStale, setDiagnosisStale] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const isDouyin = account.platform === 'douyin';

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [history, dataQuality] = await Promise.all([
        fetchHistoricalPosts(account.id), getHistoricalCompleteness(account.id),
      ]);
      setPosts(history.items);
      setCompleteness(dataQuality);
    } catch {
      setError('加载历史内容失败，请重试。');
    } finally {
      setLoading(false);
    }
  }, [account.id]);

  useEffect(() => { void load(); }, [load]);
  const openCreate = () => { setEditingId(null); setForm(emptyForm()); };
  const openEdit = (post: HistoricalPost) => { setEditingId(post.id); setForm(postToForm(post)); };

  const save = async () => {
    if (!form?.title.trim()) return;
    setSaving(true); setError('');
    try {
      const payload = formToPayload(form);
      if (editingId) await updateHistoricalPost(account.id, editingId, payload);
      else await createHistoricalPost(account.id, payload);
      setForm(null); await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存历史内容失败');
    } finally { setSaving(false); }
  };

  const remove = async (post: HistoricalPost) => {
    if (!window.confirm(`删除「${post.title}」？此操作会移除这条历史记录。`)) return;
    try { await deleteHistoricalPost(account.id, post.id); await load(); }
    catch (err) { setError(err instanceof Error ? err.message : '删除历史内容失败'); }
  };

  const chooseFile = async (file?: File) => {
    if (!file) return;
    setPreview(null); setImportMessage(''); setError('');
    try { setPreview(await previewHistoricalImport(account.id, file)); }
    catch (err) { setError(err instanceof Error ? err.message : '读取导入文件失败'); }
    finally { if (fileRef.current) fileRef.current.value = ''; }
  };

  const confirmImport = async () => {
    if (!preview) return;
    setImporting(true); setError('');
    try {
      if (preview.preview_kind === 'snapshot') {
        if (!preview.can_confirm) throw new Error('预览中有错误行，修正导出文件后再试。');
        const result = await confirmOfficialExportSnapshot(account.id, preview.preview_id);
        setImportMessage(`抖音官方导出已对账：新增 ${result.inserted_count} 条，更新 ${result.updated_count} 条，合并重复 ${result.archived_duplicate_count} 条。`);
        setDiagnosisStale(Boolean(result.diagnosis_stale));
      } else {
        const result = await confirmHistoricalImport(account.id, preview.preview_id);
        setImportMessage(`已导入 ${result.imported_count} 条，跳过重复 ${result.skipped_duplicate_count} 条，错误 ${result.error_count} 行。`);
      }
      setPreview(null); await load();
    } catch (err) { setError(err instanceof Error ? err.message : '确认导入失败'); }
    finally { setImporting(false); }
  };

  const inspectHistoricalRepair = async () => {
    setBusy(true); setError('');
    try { setRepairPreview(await previewHistoricalRepair(account.id)); setManualRepairGroups([]); }
    catch (err) { setError(err instanceof Error ? err.message : '生成历史重复修复预览失败'); }
    finally { setBusy(false); }
  };

  const confirmRepair = async () => {
    if (!repairPreview) return;
    setImporting(true); setError('');
    try {
      const result = await confirmHistoricalRepair(account.id, repairPreview.preview_id, manualRepairGroups);
      setImportMessage(`已修复并合并 ${result.archived_duplicate_count} 条重复作品（人工确认组 ${result.manual_review_confirmed} 组），保留 ${result.canonical_count} 条规范记录。`);
      setDiagnosisStale(Boolean(result.diagnosis_stale));
      setRepairPreview(null); await load();
    } catch (err) { setError(err instanceof Error ? err.message : '确认历史重复修复失败'); }
    finally { setImporting(false); }
  };

  const extraFields = isDouyin
    ? ['duration', 'subjects', 'hook_type', 'views', 'likes', 'comments', 'favorites', 'shares', 'followers_gain']
    : ['views', 'likes', 'favorites', 'comments', 'shares', 'followers_gain', 'profile_visits', 'inquiries'];
  const editableFields = ['publish_time', 'title', 'content_type', 'content_source', ...extraFields, 'tags', 'note', 'platform_post_id'];

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
        <span className="badge">有效作品 {completeness?.sample_size ?? 0} 条</span>
        <span className="badge">数据完整度 {completeness?.score ?? 0}%</span>
        {isDouyin ? <button className="btn btn-sm btn-primary" onClick={() => fileRef.current?.click()}>导入抖音作品数据</button>
          : <button className="btn btn-sm btn-primary" onClick={() => fileRef.current?.click()}>导入 CSV / XLSX</button>}
        <button className="btn btn-sm" onClick={openCreate}>+ 手动添加</button>
        {isDouyin && <button className="btn btn-sm" onClick={() => setShowOtherImport((value) => !value)}>
          其他导入方式 {showOtherImport ? '▲' : '▼'}
        </button>}
        {isDouyin && <button className="btn btn-sm" onClick={() => void inspectHistoricalRepair()} disabled={busy}>
          {busy ? '正在检查…' : '检查历史数据'}
        </button>}
        <input ref={fileRef} type="file" accept=".csv,.xlsx" hidden onChange={(event) => void chooseFile(event.target.files?.[0])} />
      </div>

      {isDouyin && <div className="page-subtitle" style={{ marginTop: 8 }}>
        请先在 PC 端抖音创作者中心 → 内容管理 / 作品管理中导出“作品列表.xlsx”，然后上传文件。
      </div>}
      {isDouyin && showOtherImport && <div className="card" style={{ marginTop: 10, padding: 12 }}>
        <button className="btn btn-sm" onClick={() => fileRef.current?.click()}>导入其他 CSV / XLSX</button>
      </div>}

      {completeness && <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-secondary)' }}>
        完整度依据样本数量、发布时间、内容类型、播放/曝光和互动数据覆盖率计算。
        {Object.entries(completeness.coverage).map(([key, value]) => <span key={key} style={{ marginLeft: 10 }}>
          {FIELD_LABELS[key] || key} {Math.round(value * 100)}%</span>)}
      </div>}
      {error && <div role="alert" style={{ color: 'var(--red)', fontSize: 13, marginTop: 12 }}>{error}</div>}
      {importMessage && <div role="status" className="card" style={{ padding: 10, marginTop: 12 }}>{importMessage}</div>}
      {diagnosisStale && onRunDiagnosis && <div className="card" style={{ marginTop: 10, padding: 10 }}>
        历史数据已更新，请重新运行账号诊断。 <button className="btn btn-sm btn-primary" onClick={onRunDiagnosis}>重新运行账号诊断</button>
      </div>}

      {preview && <div className="card" style={{ marginTop: 16, padding: 14 }}>
        {preview.preview_kind === 'snapshot' ? <>
          <h3 style={{ margin: '0 0 10px' }}>抖音创作者中心官方导出预览</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
            <span className="badge">文件记录 {preview.file_record_count}</span>
            <span className="badge">可识别 {preview.platform_unique_count}</span>
            <span className="badge">新增 {preview.insert_count}</span><span className="badge">更新 {preview.update_count}</span>
            <span className="badge">重复 {preview.duplicate_count}</span><span className="badge">错误 {preview.error_count}</span>
          </div>
          <div role="status" style={{ fontSize: 12, marginBottom: 8 }}>{preview.message}</div>
          {preview.identity_confidence === 'low' && <div style={{ fontSize: 12, marginBottom: 8, color: 'var(--red)' }}>
            当前导出文件缺少稳定作品 ID，重复匹配置信度较低；系统不会依据此文件标记其他作品缺失。
          </div>}
          {(preview.warnings || []).map((warning) => <div key={warning} style={{ fontSize: 12, marginBottom: 6 }}>{warning}</div>)}
          {!!preview.missing_fields?.length && <div style={{ fontSize: 12, marginBottom: 8 }}>
            缺失关键字段：{preview.missing_fields.map((field) => FIELD_LABELS[field.field] || field.field).join('、')}
          </div>}
          {!!preview.unsupported_columns?.length && <div style={{ fontSize: 12, marginBottom: 8 }}>
            检测到以下暂未纳入 V1 诊断的字段：{preview.unsupported_columns.join('、')}
          </div>}
          {(preview.errors || []).map((item) => <div key={item.row} style={{ color: 'var(--red)', fontSize: 12 }}>
            第 {item.row} 行「{item.title}」：{Object.values(item.errors).join('；')}
          </div>)}
          <div style={{ maxHeight: 230, overflowY: 'auto', fontSize: 12, marginTop: 8 }}>
            {preview.rows.map((row) => <div key={row.row} style={{ borderTop: '1px solid var(--border)', padding: '7px 0' }}>
              <strong>第 {row.row} 行 · {row.status === 'ready' ? '可导入' : row.status === 'update' ? '将更新' : '有错误'}</strong>
              {' · '}{String(row.record.title || '（无标题）')} · 播放 {String(row.record.views ?? '—')} · 赞 {String(row.record.likes ?? '—')}
              {Object.entries(row.errors).map(([field, message]) => <div key={field} style={{ color: 'var(--red)' }}>
                {FIELD_LABELS[field] || field}：{message}</div>)}
            </div>)}
            {preview.preview_truncated && <div>仅显示前 100 行预览。</div>}
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
            <button className="btn btn-sm" onClick={() => setPreview(null)}>取消</button>
            <button className="btn btn-sm btn-primary" onClick={() => void confirmImport()} disabled={importing || !preview.can_confirm}>
              {importing ? '正在对账…' : '确认导入并更新'}
            </button>
          </div>
        </> : <>
          <h3 style={{ margin: '0 0 10px' }}>文件导入预览</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
            <span className="badge">总行数 {preview.total_rows}</span><span className="badge badge-ok">可导入 {preview.importable_count}</span>
            <span className="badge">错误 {preview.error_count}</span><span className="badge">重复 {preview.duplicate_count}</span>
          </div>
          {!!preview.missing_fields?.length && <div style={{ fontSize: 12, marginBottom: 8 }}>
            缺失字段：{preview.missing_fields.map((item) => FIELD_LABELS[item.field] || item.field).join('、')}
          </div>}
          {!!preview.ignored_columns?.length && <div style={{ fontSize: 12, marginBottom: 8 }}>
            当前不会导入这些列：{preview.ignored_columns.join('、')}
          </div>}
          <div style={{ maxHeight: 230, overflowY: 'auto', fontSize: 12 }}>
            {preview.rows.map((row) => <div key={row.row} style={{ borderTop: '1px solid var(--border)', padding: '7px 0' }}>
              <strong>第 {row.row} 行 · {row.status === 'ready' ? '可导入' : row.status === 'duplicate' ? '重复，将跳过' : '有错误'}</strong>
              {' · '}{String(row.record.title || '（无标题）')}
              {Object.entries(row.errors).map(([field, message]) => <div key={field} style={{ color: 'var(--red)' }}>{FIELD_LABELS[field] || field}：{message}</div>)}
            </div>)}
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
            <button className="btn btn-sm" onClick={() => setPreview(null)}>取消</button>
            <button className="btn btn-sm btn-primary" onClick={() => void confirmImport()} disabled={importing || preview.importable_count === 0}>
              {importing ? '导入中…' : `确认导入 ${preview.importable_count} 条`}
            </button>
          </div>
        </>}
      </div>}

      {repairPreview && <div className="card" style={{ marginTop: 16, padding: 14 }} aria-label="历史重复修复预览">
        <h3 style={{ margin: '0 0 10px' }}>历史重复修复预览 · {account.name}</h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <span className="badge">当前记录 {repairPreview.database_current_count}</span>
          <span className="badge">估算唯一作品 {repairPreview.estimated_unique_count}</span>
          <span className="badge">重复记录 {repairPreview.duplicate_count}</span>
          <span className="badge badge-ok">可自动合并 {repairPreview.auto_merge_count}</span>
          <span className="badge">需人工确认 {repairPreview.manual_review_count}</span>
        </div>
        <div style={{ maxHeight: 200, overflowY: 'auto', marginTop: 8, fontSize: 12 }}>
          {repairPreview.groups.map((group) => <div key={group.canonical_id} style={{ borderTop: '1px solid var(--border)', padding: '6px 0' }}>
            {group.title || '（无标题）'} · 自动合并 {group.duplicate_ids.length} 条
          </div>)}
          {repairPreview.manual_review_groups.map((group) => <label key={group.group_id} style={{ display: 'flex', gap: 8, borderTop: '1px solid var(--border)', padding: '6px 0' }}>
            <input type="checkbox" checked={manualRepairGroups.includes(group.group_id)}
              onChange={(event) => setManualRepairGroups((current) => event.target.checked
                ? [...current, group.group_id] : current.filter((id) => id !== group.group_id))} />
            <span>{group.title || '（无标题）'} · 确认这 {group.count} 条为同一作品后合并</span>
          </label>)}
          {repairPreview.preview_truncated && <div>仅展示前 200 个重复组。</div>}
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
          <button className="btn btn-sm" onClick={() => setRepairPreview(null)}>关闭</button>
          <button className="btn btn-sm btn-primary" onClick={() => void confirmRepair()}
            disabled={importing || (repairPreview.auto_merge_count === 0 && manualRepairGroups.length === 0)}>
            {importing ? '修复中…' : `确认自动合并 ${repairPreview.auto_merge_count} 条${manualRepairGroups.length ? `，并合并人工确认组 ${manualRepairGroups.length} 组` : ''}`}
          </button>
        </div>
      </div>}

      {loading ? <div className="loading" style={{ padding: 22 }}>正在读取历史内容…</div> : posts.length === 0 ? (
        <div className="card" style={{ marginTop: 14, padding: 20, textAlign: 'center', color: 'var(--text-secondary)' }}>
          这个账号还没有历史作品。{isDouyin ? '请导入抖音创作者中心官方作品列表，或手动添加。' : '可以导入 CSV / XLSX 或手动添加。'}
        </div>
      ) : <HistoricalClassificationPanel account={account} onChanged={() => { setDiagnosisStale(true); void load(); }}
        onEdit={(row: HistoricalClassificationRow) => openEdit(row)} onDelete={(row: HistoricalClassificationRow) => void remove(row)}
        onOpenSettings={onOpenSettings} />}

      {form && <div className="overlay" onClick={() => setForm(null)}>
        <div className="modal" style={{ width: 620, maxWidth: '100%', maxHeight: '90vh', overflowY: 'auto' }} onClick={(event) => event.stopPropagation()}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0 }}>{editingId ? '编辑历史内容' : '人工新增历史内容'}</h3>
            <button className="icon-btn" onClick={() => setForm(null)}>×</button>
          </div>
          <p className="page-subtitle" style={{ margin: '5px 0 14px' }}>归属：{account.name}（{isDouyin ? '抖音' : '小红书'}）</p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '0 12px' }}>
            {editableFields.map((field) => <label key={field} className="field-label" style={field === 'note' ? { gridColumn: '1 / -1' } : undefined}>
              {FIELD_LABELS[field]}{field === 'title' ? ' *' : ''}
              {field === 'content_source' ? <select className="field" value={form[field]} onChange={(event) => setForm({ ...form, [field]: event.target.value })}>
                {['REAL', 'AI', 'MIXED', 'UNKNOWN'].map((value) => <option key={value}>{value}</option>)}
              </select> : field === 'note' ? <textarea className="field" value={form[field]} rows={3} onChange={(event) => setForm({ ...form, [field]: event.target.value })} /> :
                <input className="field" type={field === 'publish_time' ? 'datetime-local' : field === 'title' || ['content_type', 'tags', 'subjects', 'hook_type', 'platform_post_id'].includes(field) ? 'text' : 'number'}
                  min={field === 'followers_gain' ? undefined : 0} step={field === 'duration' ? '0.1' : '1'}
                  value={form[field]} required={field === 'title'} onChange={(event) => setForm({ ...form, [field]: event.target.value })} />}
            </label>)}
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
            <button className="btn btn-sm" onClick={() => setForm(null)}>取消</button>
            <button className="btn btn-sm btn-primary" onClick={() => void save()} disabled={saving || !form.title.trim()}>{saving ? '保存中…' : '保存'}</button>
          </div>
        </div>
      </div>}
    </section>
  );
}
