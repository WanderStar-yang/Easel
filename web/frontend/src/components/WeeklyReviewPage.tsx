import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  confirmStrategyMemory, dismissStrategyMemory, fetchFeedbackContext, fetchOperatorAccounts, fetchWeeklyReview,
  fetchWeeklyReviews, generateWeeklyReview, registerPublishedPost, savePublishedPostMetrics,
} from '../lib/api';
import type { FeedbackContext, FeedbackMemory, FeedbackPost, OperatorAccount, WeeklyReview } from '../lib/api';

const METRIC_FIELDS = [
  ['views', '播放'], ['likes', '点赞'], ['comments', '评论'], ['favorites', '收藏'],
  ['shares', '分享'], ['followers_gain', '涨粉'], ['profile_visits', '主页访问'], ['inquiries', '咨询'],
] as const;
type MetricField = (typeof METRIC_FIELDS)[number][0];
const SOURCE_LABEL: Record<string, string> = { REAL: '真实拍摄', AI: 'AI 生成', MIXED: '真人/AI 混合', UNKNOWN: '暂无法识别' };
const REVIEW_STATUS: Record<string, string> = { CURRENT: '当前版本', STALE: '数据已变化', SUPERSEDED: '历史版本' };
const METRIC_LABEL: Record<string, string> = { views: '播放', likes: '点赞', comments: '评论', favorites: '收藏', shares: '分享', engagement_rate: '互动率' };

function mondayOfWeek(value: Date): string {
  const local = new Date(value.getFullYear(), value.getMonth(), value.getDate());
  const day = (local.getDay() + 6) % 7;
  local.setDate(local.getDate() - day);
  return `${local.getFullYear()}-${String(local.getMonth() + 1).padStart(2, '0')}-${String(local.getDate()).padStart(2, '0')}`;
}

function sundayOfWeek(monday: string): string {
  const value = new Date(`${monday}T00:00:00`);
  value.setDate(value.getDate() + 6);
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '操作失败，请稍后重试。';
}

function localDateTimeInput(): string {
  const value = new Date();
  const pad = (part: number) => String(part).padStart(2, '0');
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`;
}

function checkpointAvailable(publishedAt: string, checkpoint: '24H' | '72H' | '7D'): boolean {
  const hours = checkpoint === '24H' ? 24 : checkpoint === '72H' ? 72 : 168;
  return Date.now() >= new Date(publishedAt).getTime() + hours * 60 * 60 * 1000;
}

function MetricForm({ accountId, post, checkpoint, onSaved }: {
  accountId: string; post: FeedbackPost; checkpoint: '24H' | '72H' | '7D'; onSaved: () => void;
}) {
  const existing = post.metrics.find((metric) => metric.checkpoint === checkpoint);
  const available = checkpointAvailable(post.published_at, checkpoint);
  const [values, setValues] = useState<Record<MetricField, string>>(() => Object.fromEntries(
    METRIC_FIELDS.map(([field]) => [field, existing?.[field] == null ? '' : String(existing[field])]),
  ) as Record<MetricField, string>);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const save = async () => {
    const payload = Object.fromEntries(METRIC_FIELDS.map(([field]) => [
      field, values[field].trim() === '' ? null : Number(values[field]),
    ])) as Record<MetricField, number | null>;
    setBusy(true); setMessage('');
    try {
      await savePublishedPostMetrics(accountId, post.id, checkpoint, payload);
      setMessage('已保存'); onSaved();
    } catch (error) { setMessage(errorMessage(error)); }
    finally { setBusy(false); }
  };
  return <details className="card" style={{ padding: 10 }}>
    <summary style={{ cursor: 'pointer', fontWeight: 600 }}>{checkpoint} 指标{existing ? ' · 已录入' : available ? ' · 待录入' : ' · 等待数据'}</summary>
    {!available && !existing && <div className="page-subtitle" style={{ marginTop: 8 }}>发布满对应时间后再录入，当前不需要补填。</div>}
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(115px, 1fr))', gap: 8, marginTop: 10 }}>
      {METRIC_FIELDS.map(([field, label]) => <label key={field} className="field-label">{label}
        <input className="input" type="number" min={field === 'followers_gain' ? undefined : 0} step="1"
          value={values[field]} onChange={(event) => setValues((current) => ({ ...current, [field]: event.target.value }))}
          placeholder="留空表示未知" />
      </label>)}
    </div>
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 8 }}>
      <button className="btn btn-sm btn-primary" disabled={busy || (!available && !existing)} onClick={() => void save()}>{busy ? '保存中…' : '保存指标'}</button>
      <span className="page-subtitle">{message || '未知数据留空；真实的 0 填写 0。'}</span>
    </div>
  </details>;
}

function metricText(metrics: Record<string, unknown> | undefined, name: string): string {
  const metric = metrics?.[name];
  if (!metric || typeof metric !== 'object') return '—';
  const value = metric as { median?: unknown; sample_count?: unknown; relative_to_baseline?: unknown };
  const median = typeof value.median === 'number' ? (name === 'engagement_rate' ? `${(value.median * 100).toFixed(2)}%` : String(value.median)) : '—';
  const delta = typeof value.relative_to_baseline === 'number' ? `（较基准 ${value.relative_to_baseline >= 0 ? '+' : ''}${(value.relative_to_baseline * 100).toFixed(1)}%）` : '';
  return `${median}${delta} · ${String(value.sample_count ?? 0)} 条有效作品`;
}

function MemoryCard({ memory, onDecision }: { memory: FeedbackMemory; onDecision: (id: string, confirm: boolean) => void }) {
  const [statement, setStatement] = useState(memory.statement);
  const [busy, setBusy] = useState(false);
  const save = async (confirm: boolean) => {
    setBusy(true);
    try { await onDecision(memory.id, confirm); } finally { setBusy(false); }
  };
  return <article className="card" style={{ padding: 12, display: 'grid', gap: 8 }}>
    <label className="field-label">待确认的经验<textarea className="input" rows={3} value={statement} onChange={(event) => setStatement(event.target.value)} /></label>
    <div className="page-subtitle">依据：{String(memory.evidence.scope_name || '—')} · {METRIC_LABEL[String(memory.evidence.metric)] || '相关指标'} · {String(memory.evidence.sample_size || 0)} 条作品 · 差异仅作描述性观察。</div>
    <div style={{ display: 'flex', gap: 8 }}>
      <button className="btn btn-sm btn-primary" disabled={busy} onClick={() => void save(true)}>确认并加入后续选题参考</button>
      <button className="btn btn-sm" disabled={busy} onClick={() => void save(false)}>忽略</button>
    </div>
  </article>;
}

export default function WeeklyReviewPage() {
  const [accounts, setAccounts] = useState<OperatorAccount[]>([]);
  const [accountId, setAccountId] = useState('');
  const [context, setContext] = useState<FeedbackContext | null>(null);
  const [reviews, setReviews] = useState<WeeklyReview[]>([]);
  const [review, setReview] = useState<WeeklyReview | null>(null);
  const [weekStart, setWeekStart] = useState(() => mondayOfWeek(new Date()));
  const [selectedTopic, setSelectedTopic] = useState('');
  const [postForm, setPostForm] = useState({ title: '', published_url: '', platform_post_id: '', published_at: localDateTimeInput(), content_source: 'UNKNOWN', hook_type: '', duration_seconds: '' });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const refresh = useCallback(async (id: string) => {
    if (!id) return;
    setLoading(true); setError('');
    try {
      const [nextContext, nextReviews] = await Promise.all([fetchFeedbackContext(id), fetchWeeklyReviews(id)]);
      setContext(nextContext); setReviews(nextReviews);
      setReview((current) => current ? nextReviews.find((item) => item.id === current.id) || current : null);
      setSelectedTopic((current) => current || nextContext.selected_topics[0]?.id || '');
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    fetchOperatorAccounts().then((items) => {
      setAccounts(items);
      const first = items.find((item) => item.status === 'ACTIVE') || items[0];
      if (first) setAccountId(first.id);
      else setLoading(false);
    }).catch((reason: unknown) => { setError(errorMessage(reason)); setLoading(false); });
  }, []);
  useEffect(() => { if (accountId) void refresh(accountId); }, [accountId, refresh]);

  const topics = context?.selected_topics || [];
  const activeMemories = context?.active_memories || [];
  const proposalMemories = useMemo(() => review?.memories?.filter((item) => item.status === 'PROPOSED') || [], [review]);
  const selectedReviewReport = review?.report || {};
  const checkpointSummaries = (selectedReviewReport.checkpoint_summaries || {}) as Record<string, {
    post_count: number; metrics: Record<string, unknown>; groups: Record<string, Array<Record<string, unknown>>>;
  }>;
  const thisWeekPosts = context?.published_posts.filter((post) =>
    post.published_at.slice(0, 10) >= weekStart && post.published_at.slice(0, 10) <= sundayOfWeek(weekStart),
  ) ?? [];
  const postsThisWeek = thisWeekPosts.length;
  const reviewablePosts = thisWeekPosts.filter((post) => post.metrics.length > 0).length;

  const submitPost = async () => {
    if (!accountId || !selectedTopic) { setError('先选择一个当前策略下已确认的选题。'); return; }
    const topic = topics.find((item) => item.id === selectedTopic);
    if (!topic) return;
    setBusy(true); setError(''); setNotice('');
    try {
      await registerPublishedPost(accountId, {
        topic_id: topic.id, draft_id: topic.draft_id, title: postForm.title.trim() || topic.title,
        published_url: postForm.published_url.trim() || null, platform_post_id: postForm.platform_post_id.trim() || null,
        published_at: new Date(postForm.published_at).toISOString(),
        content_source: postForm.content_source, hook_type: postForm.hook_type.trim() || null,
        duration_seconds: postForm.duration_seconds ? Number(postForm.duration_seconds) : null,
      });
      setPostForm((current) => ({ ...current, title: '', published_url: '', platform_post_id: '', hook_type: '', duration_seconds: '' }));
      setNotice('发布记录已保存。请在作品卡片中按真实情况补录 24H / 72H / 7D 指标。');
      await refresh(accountId);
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  };

  const runReview = async () => {
    setBusy(true); setError(''); setNotice('');
    try {
      const next = await generateWeeklyReview(accountId, weekStart);
      setReview(next); setNotice(`周复盘 V${next.version} 已生成，未确认的经验不会进入后续选题。`);
      await refresh(accountId);
      setReview(next);
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  };

  const decideMemory = async (memoryId: string, confirm: boolean) => {
    try {
      if (confirm) await confirmStrategyMemory(accountId, memoryId, proposalMemories.find((item) => item.id === memoryId)?.statement);
      else await dismissStrategyMemory(accountId, memoryId);
      if (review) setReview(await fetchWeeklyReview(accountId, review.id));
      await refresh(accountId);
    } catch (reason) { setError(errorMessage(reason)); throw reason; }
  };

  const loadReview = async (item: WeeklyReview) => {
    setBusy(true); setError('');
    try { setReview(await fetchWeeklyReview(accountId, item.id)); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  };

  return <div className="page" style={{ display: 'grid', gap: 16, maxWidth: 1100 }}>
    <header>
      <h1 style={{ marginBottom: 4 }}>周复盘</h1>
      <div className="page-subtitle">只分析手动登记的真实发布和平台指标。复盘不会自动修改已确认策略；经验经你确认后才进入后续选题。</div>
    </header>

    <section className="card" style={{ padding: 14, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'end' }}>
      <label className="field-label">运营账号<select className="input" value={accountId} onChange={(event) => { setContext(null); setReview(null); setAccountId(event.target.value); }}>
        {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
      </select></label>
      <label className="field-label">复盘周（周一）<input className="input" type="date" value={weekStart} onChange={(event) => setWeekStart(event.target.value)} /></label>
      <button className="btn btn-primary" disabled={busy || loading || reviewablePosts < 3} onClick={() => void runReview()}>{busy ? '处理中…' : '生成本周复盘'}</button>
      <span className="page-subtitle">历史基准：{context?.baseline?.status === 'ACTIVE' ? `V${context.baseline.version}` : '当前不可用'} · 本周已登记 {postsThisWeek} 条作品</span>
    </section>

    {!loading && reviewablePosts < 3 && <div className="card page-subtitle" style={{ padding: 14 }}>
      当前发布样本不足，暂无法形成有效周复盘。已登记 {postsThisWeek} 条，本周有实际指标的作品 {reviewablePosts} 条；需要至少 3 条有数据的发布作品。
    </div>}

    {error && <div className="card" role="alert" style={{ padding: 12, color: 'var(--red)' }}>{error}</div>}
    {notice && <div className="card" role="status" style={{ padding: 12 }}>{notice}</div>}
    {loading && <div className="page-subtitle">正在读取账号发布记录…</div>}

    {context && <>
      <section className="card" style={{ padding: 14, display: 'grid', gap: 12 }}>
        <div><h2 style={{ margin: 0 }}>登记已发布作品</h2><div className="page-subtitle">仅登记人工发布的内容。系统不调用平台发布接口。作品必须关联当前策略下已选择的选题。</div></div>
        {!topics.length ? <div className="page-subtitle">当前策略下没有可关联的已选择选题。</div> : <>
          <label className="field-label">已选择选题<select className="input" value={selectedTopic} onChange={(event) => {
            setSelectedTopic(event.target.value); const topic = topics.find((item) => item.id === event.target.value);
            if (topic) setPostForm((current) => ({ ...current, title: topic.title }));
          }}>
            {topics.map((topic) => <option key={topic.id} value={topic.id}>{topic.title} · {topic.pillar_name}</option>)}
          </select></label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
            <label className="field-label">作品标题<input className="input" value={postForm.title} onChange={(event) => setPostForm({ ...postForm, title: event.target.value })} /></label>
            <label className="field-label">实际发布时间<input className="input" type="datetime-local" value={postForm.published_at} onChange={(event) => setPostForm({ ...postForm, published_at: event.target.value })} /></label>
            <label className="field-label">内容来源<select className="input" value={postForm.content_source} onChange={(event) => setPostForm({ ...postForm, content_source: event.target.value })}>
              <option value="UNKNOWN">无法判断</option><option value="REAL">真实拍摄</option><option value="AI">AI 生成</option><option value="MIXED">真人/AI 混合</option>
            </select></label>
            <label className="field-label">Hook 类型（可选）<input className="input" value={postForm.hook_type} onChange={(event) => setPostForm({ ...postForm, hook_type: event.target.value })} placeholder="例如：提问" /></label>
            <label className="field-label">视频时长（秒，可选）<input className="input" type="number" min="1" value={postForm.duration_seconds} onChange={(event) => setPostForm({ ...postForm, duration_seconds: event.target.value })} /></label>
            <label className="field-label">作品链接（可选）<input className="input" value={postForm.published_url} onChange={(event) => setPostForm({ ...postForm, published_url: event.target.value })} /></label>
            <label className="field-label">平台作品 ID（可选）<input className="input" value={postForm.platform_post_id} onChange={(event) => setPostForm({ ...postForm, platform_post_id: event.target.value })} /></label>
          </div>
          <div><button className="btn btn-sm btn-primary" disabled={busy} onClick={() => void submitPost()}>保存已发布作品</button></div>
        </>}
      </section>

      <section style={{ display: 'grid', gap: 10 }}>
        <h2 style={{ margin: 0 }}>发布记录与分时指标</h2>
        {!context.published_posts.length && <div className="card page-subtitle" style={{ padding: 14 }}>还没有已登记的发布作品。发布后请在这里记录，并按平台实际数据录入各节点。</div>}
        {context.published_posts.map((post) => <article className="card" key={post.id} style={{ padding: 12, display: 'grid', gap: 8 }}>
          <strong>{post.title}</strong>
          <div className="page-subtitle">{post.pillar_name || '未关联方向'} · {post.published_at} · 来源 {SOURCE_LABEL[post.content_source] || '暂无法识别'} · {post.duration_seconds ? `${post.duration_seconds} 秒` : '时长未知'}</div>
          {(['24H', '72H', '7D'] as const).map((checkpoint) => <MetricForm key={`${post.id}-${checkpoint}`} accountId={accountId} post={post} checkpoint={checkpoint} onSaved={() => void refresh(accountId)} />)}
        </article>)}
      </section>

      {!!reviews.length && <section className="card" style={{ padding: 14, display: 'grid', gap: 8 }}>
        <h2 style={{ margin: 0 }}>复盘历史</h2>
        {reviews.map((item) => <button key={item.id} className="btn" style={{ textAlign: 'left' }} disabled={busy} onClick={() => void loadReview(item)}>
          {item.week_start} ～ {item.week_end} · V{item.version} · {REVIEW_STATUS[item.status] || '历史版本'}
        </button>)}
      </section>}

      {review && <section className="card" style={{ padding: 14, display: 'grid', gap: 14 }}>
        <div><h2 style={{ margin: 0 }}>周复盘 V{review.version} · {review.week_start} ～ {review.week_end}</h2>
          <div className="page-subtitle">状态：{REVIEW_STATUS[review.status] || '历史版本'} · 基于 {String(selectedReviewReport.published_count || 0)} 条实际发布。历史基准：{(selectedReviewReport.baseline as Record<string, unknown> | undefined)?.status === 'ACTIVE' ? '可用' : '当前不可用'}。</div>
        </div>
        <div className="page-subtitle">{Array.isArray(selectedReviewReport.notes) ? selectedReviewReport.notes.join(' ') : ''}</div>
        {typeof selectedReviewReport.explanation === 'object' && selectedReviewReport.explanation !== null && <div className="card" style={{ padding: 12, display: 'grid', gap: 6 }}>
          <strong>本周怎么理解</strong>
          <div>{String((selectedReviewReport.explanation as Record<string, unknown>).summary || '继续积累真实发布数据。')}</div>
          {Array.isArray((selectedReviewReport.explanation as Record<string, unknown>).observations) && ((selectedReviewReport.explanation as Record<string, unknown>).observations as unknown[]).map((item, index) => <div className="page-subtitle" key={index}>{String(item)}</div>)}
        </div>}
        {Object.entries(checkpointSummaries).map(([checkpoint, summary]) => <div key={checkpoint}>
          <h3 style={{ margin: '4px 0' }}>{checkpoint} · {summary.post_count} 条</h3>
          <div className="page-subtitle">播放中位数 {metricText(summary.metrics, 'views')}；点赞中位数 {metricText(summary.metrics, 'likes')}；互动率中位数 {metricText(summary.metrics, 'engagement_rate')}</div>
          {summary.groups?.content_pillar?.length > 0 && <div className="page-subtitle" style={{ marginTop: 6 }}>
            按内容方向：{summary.groups.content_pillar.map((group) => `${String(group.label)} · ${String(group.sample_size)} 条作品，播放 ${metricText(group.metrics as Record<string, unknown>, 'views')}，互动率 ${metricText(group.metrics as Record<string, unknown>, 'engagement_rate')}`).join('；')}
          </div>}
        </div>)}
        <div><h3 style={{ margin: '4px 0' }}>下周观察</h3>{Array.isArray(selectedReviewReport.next_week_suggestions) && selectedReviewReport.next_week_suggestions.map((suggestion) => <div className="page-subtitle" key={String(suggestion)}>{String(suggestion)}</div>)}</div>
        <div><h3 style={{ margin: '4px 0' }}>待你确认的经验</h3>
          {!proposalMemories.length && <div className="page-subtitle">当前样本未达到形成长期经验建议的门槛；不会自动写入后续选题。</div>}
          {proposalMemories.map((memory) => <MemoryCard key={memory.id} memory={memory} onDecision={decideMemory} />)}
        </div>
      </section>}

      <section className="card" style={{ padding: 14, display: 'grid', gap: 8 }}>
        <h2 style={{ margin: 0 }}>已确认的长期经验</h2>
        {!activeMemories.length && <div className="page-subtitle">暂无已确认经验。复盘提出的观察需经你确认后，才会作为下一轮选题的验证线索。</div>}
        {activeMemories.map((memory) => <div className="page-subtitle" key={memory.id}>• {memory.statement}</div>)}
      </section>
    </>}
  </div>;
}
