import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  acceptHistoricalClassificationSuggestions, batchClassifyHistoricalPosts,
  fetchHistoricalClassificationProgress, fetchHistoricalClassificationRows, fetchHistoricalClassificationRuntime,
  runHistoricalAIPreclassification,
} from '../lib/api';
import type { AIRuntimeStatus, HistoricalClassificationProgress, HistoricalClassificationRow } from '../lib/api';
import type { OperatorAccount } from '../lib/api';

const FIELDS = ['content_source', 'subjects', 'content_type'] as const;
const LABELS: Record<string, string> = { content_source: '内容来源', subjects: '出镜主体', content_type: '内容类型' };
const SOURCE_LABELS: Record<string, string> = { REAL: '真实拍摄', AI: 'AI生成', MIXED: '真人/AI混合', UNKNOWN: '无法判断' };
const TYPE_OPTIONS = ['单猫日常', '双猫互动', '双猫反差', '搞笑/趣味', '养猫经验', '情绪/陪伴', 'AI创意', '其他'];
const SUBJECT_OPTIONS = ['缅因', '布偶', '双猫', '其他', 'UNKNOWN'];
const CONFIDENCE_LABELS: Record<string, string> = { HIGH: '高', MEDIUM: '中', LOW: '低' };
type ViewFilter = 'all' | 'unclassified' | 'subjects_unclassified' | 'low' | 'suggested';

function textValue(value: unknown, field?: string): string {
  if (Array.isArray(value)) return value.map((item) => String(item)).join('、') || '—';
  if (typeof value !== 'string' || !value) return '—';
  return field === 'content_source' ? SOURCE_LABELS[value] || value : value === 'UNKNOWN' ? '无法判断' : value;
}

function hasClassification(row: HistoricalClassificationRow, field: string): boolean {
  if (field === 'content_source') return row.content_source !== 'UNKNOWN';
  if (field === 'subjects') return row.subjects.length > 0 && !row.subjects.includes('UNKNOWN');
  return Boolean(row.content_type && row.content_type !== 'UNKNOWN');
}

function hasLowConfidence(row: HistoricalClassificationRow): boolean {
  return Object.values(row.suggestions).some((suggestion) => suggestion.confidence === 'LOW');
}

function hasSuggestions(row: HistoricalClassificationRow): boolean {
  return row.suggestion_status === 'SUGGESTED' && Object.keys(row.suggestions).length > 0;
}

function Progress({ progress }: { progress: HistoricalClassificationProgress | null }) {
  if (!progress) return null;
  const entries = [
    ['内容来源', progress.content_source], ['出镜主体', progress.subjects], ['内容类型', progress.content_type],
  ] as const;
  return <div className="card" style={{ padding: 12, marginTop: 12 }}>
    <strong>历史作品分类进度</strong>
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
      {entries.map(([label, metric]) => <span className="badge" key={label}>
        {label}：{metric.classified_count} / {metric.sample_size}（{Math.round(metric.coverage * 100)}%）
      </span>)}
    </div>
  </div>;
}

export default function HistoricalClassificationPanel({ account, onChanged, onEdit, onDelete, onOpenSettings }: {
  account: OperatorAccount;
  onChanged: () => void;
  onEdit: (row: HistoricalClassificationRow) => void;
  onDelete: (row: HistoricalClassificationRow) => void;
  onOpenSettings: () => void;
}) {
  const [rows, setRows] = useState<HistoricalClassificationRow[]>([]);
  const [progress, setProgress] = useState<HistoricalClassificationProgress | null>(null);
  const [runtime, setRuntime] = useState<AIRuntimeStatus | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [filter, setFilter] = useState<ViewFilter>('all');
  const [source, setSource] = useState('');
  const [subject, setSubject] = useState('');
  const [contentType, setContentType] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [confirmHigh, setConfirmHigh] = useState(false);

  const load = useCallback(async () => {
    try {
      const [classificationRows, completion, aiRuntime] = await Promise.all([
        fetchHistoricalClassificationRows(account.id), fetchHistoricalClassificationProgress(account.id),
        fetchHistoricalClassificationRuntime(account.id),
      ]);
      setRows(classificationRows.items);
      setProgress(completion);
      setRuntime(aiRuntime);
      setSelected((current) => current.filter((id) => classificationRows.items.some((row) => row.id === id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : '读取历史作品分类失败');
    }
  }, [account.id]);

  useEffect(() => { void load(); }, [load]);

  const visibleRows = useMemo(() => rows.filter((row) => {
    if (filter === 'unclassified') return FIELDS.some((field) => !hasClassification(row, field));
    if (filter === 'subjects_unclassified') return !hasClassification(row, 'subjects');
    if (filter === 'low') return hasLowConfidence(row);
    if (filter === 'suggested') return hasSuggestions(row);
    return true;
  }), [rows, filter]);

  const highConfidence = useMemo(() => {
    const postIds: string[] = [];
    let fieldsCount = 0;
    for (const row of rows) {
      // Phase 5.2 only accepts subject suggestions; do not change other fields.
      const available = (['subjects'] as const).filter((field) => row.suggestions[field]?.confidence === 'HIGH'
        && row.metadata[field]?.source !== 'MANUAL_CONFIRMED');
      if (available.length) { postIds.push(row.id); fieldsCount += available.length; }
    }
    return { postIds, fieldsCount };
  }, [rows]);

  const runAI = async () => {
    setBusy(true); setError(''); setMessage('');
    try {
      const status = runtime || await fetchHistoricalClassificationRuntime(account.id);
      setRuntime(status);
      if (status.state === 'NOT_CONFIGURED') {
        setError('尚未配置 AI 模型，请先完成模型设置。');
        return;
      }
      if (status.state === 'UNAVAILABLE') {
        setError('当前 AI 服务暂时不可用。你仍可手动批量分类历史作品。');
        return;
      }
      if (status.state === 'ERROR') {
        setError('AI 模型配置或连接发生错误，请检查模型设置。你仍可手动批量分类历史作品。');
        return;
      }
      const result = await runHistoricalAIPreclassification(account.id, ['subjects']);
      setMessage(`主体专属 AI 预分类已处理：${result.suggested_post_count} 条作品、${result.suggested_field_count} 项主体建议，其中 ${result.high_confidence_field_count} 项置信度高。${result.failed_post_count ? `${result.failed_post_count} 条未能解析，` : ''}内容来源和内容类型未重新判断；所有建议仍需你确认。`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI 预分类失败；请检查 Easel 模型网关后重试。');
    } finally { setBusy(false); }
  };

  const quickSetSubject = async (value: string) => {
    if (!selected.length) return;
    if (!window.confirm(`将 ${selected.length} 条所选作品的出镜主体人工确认设为“${value}”，继续吗？`)) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const result = await batchClassifyHistoricalPosts(account.id, { post_ids: selected, subjects: [value] });
      setMessage(`已人工确认 ${result.updated_count} 条作品的出镜主体。历史基准已标记为需要更新。`);
      setSelected([]); await load(); onChanged();
    } catch (err) { setError(err instanceof Error ? err.message : '批量确认出镜主体失败'); }
    finally { setBusy(false); }
  };

  const subjectsProgress = progress?.subjects;
  const remainingTo75 = subjectsProgress
    ? Math.max(0, Math.ceil(subjectsProgress.sample_size * 0.75) - subjectsProgress.classified_count) : null;

  const applyManual = async () => {
    const payload: { post_ids: string[]; content_source?: 'REAL' | 'AI' | 'MIXED' | 'UNKNOWN'; content_type?: string; subjects?: string[] } = { post_ids: selected };
    if (source) payload.content_source = source as 'REAL' | 'AI' | 'MIXED' | 'UNKNOWN';
    if (subject) payload.subjects = subject === 'UNKNOWN' ? [] : [subject];
    if (contentType) payload.content_type = contentType;
    if (Object.keys(payload).length === 1) { setError('请选择要批量设置的分类。'); return; }
    if (!window.confirm(`将为 ${selected.length} 条作品人工确认所选分类，继续吗？`)) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const result = await batchClassifyHistoricalPosts(account.id, payload);
      setMessage(`已人工确认 ${result.updated_count} 条作品。历史基准已标记为需要更新。`);
      setSelected([]); setSource(''); setSubject(''); setContentType('');
      await load(); onChanged();
    } catch (err) { setError(err instanceof Error ? err.message : '批量设置失败'); }
    finally { setBusy(false); }
  };

  const acceptSuggestions = async (postIds: string[], highOnly: boolean, fields: readonly string[] = FIELDS) => {
    if (!postIds.length) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const result = await acceptHistoricalClassificationSuggestions(account.id, {
        post_ids: postIds, fields: [...fields], high_confidence_only: highOnly,
      });
      setMessage(`已确认 ${result.updated_count} 条作品中的 ${result.confirmed_field_count} 项 AI 建议。历史基准已标记为需要更新。`);
      setConfirmHigh(false); setSelected([]); await load(); onChanged();
    } catch (err) { setError(err instanceof Error ? err.message : '接受 AI 建议失败'); }
    finally { setBusy(false); }
  };

  const selectedSuggestions = rows.filter((row) => selected.includes(row.id) && hasSuggestions(row)).map((row) => row.id);
  const toggleAll = () => setSelected(visibleRows.length > 0 && visibleRows.every((row) => selected.includes(row.id))
    ? selected.filter((id) => !visibleRows.some((row) => row.id === id))
    : [...new Set([...selected, ...visibleRows.map((row) => row.id)])]);

  return <section aria-label="历史作品批量分类" style={{ marginTop: 14 }}>
    <Progress progress={progress} />
    {subjectsProgress && <div className="page-subtitle" style={{ marginTop: 8 }}>
      当前出镜主体覆盖：{Math.round(subjectsProgress.coverage * 100)}%；距离 75% 覆盖参考约还需确认 {remainingTo75} 条。此数字仅供整理进度参考，无法从文本可靠判断的作品应继续保留“无法判断”。
    </div>}
    <div className="card" style={{ padding: 14, marginTop: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
        <div><h3 style={{ margin: 0, fontSize: 15 }}>历史作品批量分类</h3>
          <div className="page-subtitle" style={{ marginTop: 4 }}>AI 只读取标题、原始作品类型、已有标签和描述，不会读取播放或互动数据。</div></div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span className="badge">AI模型：{runtime?.state === 'AVAILABLE' ? `${runtime.provider || '已配置'} · 可用`
            : runtime?.state === 'NOT_CONFIGURED' ? '未配置'
              : runtime?.state === 'ERROR' ? '发生错误' : runtime?.state === 'UNAVAILABLE' ? '暂时不可用' : '检查中…'}</span>
          {runtime?.state !== 'AVAILABLE' && <button className="btn btn-sm" onClick={onOpenSettings}>配置模型</button>}
          <button className="btn btn-sm btn-primary" onClick={() => void runAI()} disabled={busy || rows.length === 0 || !runtime}>
          {busy ? '正在处理…' : 'AI预分类未确认主体'}
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginTop: 12 }}>
        {([['all', '全部作品'], ['unclassified', '只看未分类'], ['subjects_unclassified', '只看出镜主体未分类'], ['low', '只看低置信度'], ['suggested', '只看 AI 建议']] as const).map(([value, label]) =>
          <button className={`btn btn-sm ${filter === value ? 'btn-primary' : ''}`} key={value} onClick={() => setFilter(value)}>{label}</button>)}
        <span className="badge">当前显示 {visibleRows.length} / {rows.length}</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'end', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
        <label className="field-label">批量设置内容来源
          <select className="field" value={source} onChange={(event) => setSource(event.target.value)}>
            <option value="">不修改</option><option value="REAL">真实拍摄</option><option value="AI">AI生成</option>
            <option value="MIXED">真人/AI混合</option><option value="UNKNOWN">暂无法判断</option>
          </select>
        </label>
        <label className="field-label">批量设置出镜主体
          <select className="field" value={subject} onChange={(event) => setSubject(event.target.value)}>
            <option value="">不修改</option>{SUBJECT_OPTIONS.map((value) => <option key={value} value={value}>{value === 'UNKNOWN' ? '无法判断' : value}</option>)}
          </select>
        </label>
        <label className="field-label">批量设置内容类型
          <select className="field" value={contentType} onChange={(event) => setContentType(event.target.value)}>
            <option value="">不修改</option>{TYPE_OPTIONS.map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <button className="btn btn-sm btn-primary" disabled={busy || !selected.length} onClick={() => void applyManual()}>
          确认所选 {selected.length} 条
        </button>
        {SUBJECT_OPTIONS.filter((value) => value !== 'UNKNOWN').map((value) => <button className="btn btn-sm" key={`quick-${value}`}
          disabled={busy || !selected.length} onClick={() => void quickSetSubject(value)}>
          设为{value} ({selected.length})
        </button>)}
        <button className="btn btn-sm" disabled={busy || !selectedSuggestions.length} onClick={() => void acceptSuggestions(selectedSuggestions, false)}>
          接受所选 AI 建议 ({selectedSuggestions.length})
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
        <button className="btn btn-sm" disabled={busy || !highConfidence.fieldsCount} onClick={() => setConfirmHigh(true)}>
          全部接受高置信度建议
        </button>
        {confirmHigh && <div role="alertdialog" aria-label="确认接受高置信度建议" className="card" style={{ padding: 10 }}>
          将确认 {highConfidence.postIds.length} 条作品中的 {highConfidence.fieldsCount} 项分类建议。
          <button className="btn btn-sm btn-primary" style={{ marginLeft: 8 }} disabled={busy}
            onClick={() => void acceptSuggestions(highConfidence.postIds, true, ['subjects'])}>确认接受</button>
          <button className="btn btn-sm" style={{ marginLeft: 6 }} onClick={() => setConfirmHigh(false)}>取消</button>
        </div>}
      </div>

      {error && <div role="alert" style={{ color: 'var(--red)', marginTop: 10, fontSize: 13 }}>{error}</div>}
      {message && <div role="status" className="card" style={{ padding: 9, marginTop: 10, fontSize: 13 }}>{message}</div>}

      <div style={{ overflowX: 'auto', maxHeight: 540, overflowY: 'auto', marginTop: 12 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, minWidth: 900 }}>
          <thead style={{ position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>
            <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border)' }}>
              <th style={{ padding: 8 }}><input aria-label="选择当前显示作品" type="checkbox"
                checked={visibleRows.length > 0 && visibleRows.every((row) => selected.includes(row.id))} onChange={toggleAll} /></th>
              <th style={{ padding: 8 }}>标题 · 播放</th><th style={{ padding: 8 }}>内容来源</th>
              <th style={{ padding: 8 }}>出镜主体</th><th style={{ padding: 8 }}>内容类型</th>
              <th style={{ padding: 8 }}>AI 置信度</th><th style={{ padding: 8 }}>操作</th>
            </tr>
          </thead>
          <tbody>{visibleRows.map((row) => <tr key={row.id} style={{ borderBottom: '1px solid var(--border)' }}>
            <td style={{ padding: 8, verticalAlign: 'top' }}><input aria-label={`选择作品 ${row.title}`} type="checkbox"
              checked={selected.includes(row.id)} onChange={(event) => setSelected((current) => event.target.checked
                ? [...current, row.id] : current.filter((id) => id !== row.id))} /></td>
            <td style={{ padding: 8, verticalAlign: 'top', maxWidth: 280 }}><strong>{row.title}</strong>
              <div className="page-subtitle" style={{ marginTop: 3 }}>播放 {row.views ?? '—'}</div></td>
            {FIELDS.map((field) => {
              const current = field === 'content_source' ? row.content_source : field === 'subjects' ? row.subjects : row.content_type;
              const suggestion = row.suggestions[field];
              const meta = row.metadata[field];
              return <td key={field} style={{ padding: 8, verticalAlign: 'top' }}>
                <div>{textValue(current, field)}</div>
                {meta?.source && <div className="page-subtitle" style={{ marginTop: 3 }}>
                  {meta.source === 'MANUAL_CONFIRMED' ? '人工确认' : meta.source === 'AI_CONFIRMED' ? '已接受 AI 建议' : '导入数据'}
                </div>}
                {suggestion && <div style={{ marginTop: 4, color: 'var(--text-secondary)' }}>
                  建议：{textValue(suggestion.value, field)} · {CONFIDENCE_LABELS[suggestion.confidence] || '低'}
                </div>}
              </td>;
            })}
            <td style={{ padding: 8, verticalAlign: 'top' }}>
              {FIELDS.filter((field) => row.suggestions[field]).map((field) => <div key={field}>
                {LABELS[field]} {CONFIDENCE_LABELS[row.suggestions[field].confidence] || '低'}
              </div>)}
              {!Object.keys(row.suggestions).length && '—'}
            </td>
            <td style={{ padding: 8, verticalAlign: 'top', whiteSpace: 'nowrap' }}>
              <button className="btn btn-sm" onClick={() => onEdit(row)}>编辑</button>
              <button className="btn btn-sm btn-ghost" onClick={() => onDelete(row)}>删除</button>
            </td>
          </tr>)}</tbody>
        </table>
        {!visibleRows.length && <div className="page-subtitle" style={{ padding: 18, textAlign: 'center' }}>当前条件下没有作品。</div>}
      </div>
    </div>
  </section>;
}
