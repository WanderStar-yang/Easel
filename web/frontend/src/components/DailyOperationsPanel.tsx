import { useCallback, useEffect, useState } from 'react';
import {
  fetchDailyTopics, fetchFeedbackContext, fetchOperatorCalendar, fetchOperatorAccounts, generateDailyTopics, selectDailyTopic,
  fetchOperatorContentDraft, generateOperatorContentDraft, updateOperatorContentDraft,
} from '../lib/api';
import type { ContentDraftContext, DailyTopic, DailyTopicAccountState, FeedbackPost, OperatorAccount } from '../lib/api';
import type { Page } from './Sidebar';

interface Props {
  onNavigate: (page: Page) => void;
}

const DIFFICULTY: Record<DailyTopic['production_difficulty'], string> = {
  EASY: '较轻', MEDIUM: '一般', HARD: '较高',
};

const DRAFT_LABELS: Record<string, string> = {
  content_theme: '内容主题', recommendation_reason: '为什么这样设计', content_goal: '内容目标',
  hook: 'Hook', opening_3_seconds: '前 3 秒设计', video_structure: '视频结构',
  shot_suggestions: '镜头建议', subtitles: '字幕', suggested_duration_seconds: '建议时长（秒）',
  title_candidates: '标题候选', bgm_type: 'BGM 类型', hashtags: '话题标签',
  comment_interaction: '评论区互动', posting_time_suggestion: '发布时间建议',
  recommended_topics: '推荐话题',
  existing_materials_to_verify: '请核对是否已有的素材', experiment_tag: '实验标签',
  cover_text: '封面文字', opening_hook: '开头 Hook', content_structure: '内容结构',
  body_markdown: '完整正文', image_structure: '配图结构', screenshot_suggestions: '截图建议',
  project_materials: '项目素材（请核实真实性）', cta: 'CTA',
};

function DraftValue({ value }: { value: unknown }) {
  if (Array.isArray(value)) {
    return <div style={{ display: 'grid', gap: 6 }}>
      {value.map((item, index) => <div className="page-subtitle" key={index}>
        {item && typeof item === 'object'
          ? <div style={{ display: 'grid', gap: 3 }}>{Object.entries(item).map(([key, part]) =>
            <div key={key}><strong>{({ time_range: '时间', visual: '画面', narration: '口播', subtitle: '字幕' } as Record<string, string>)[key] || key}：</strong>{String(part)}</div>)}</div>
          : <div>{value.length > 1 ? `${index + 1}. ` : ''}{String(item)}</div>}
      </div>)}
    </div>;
  }
  return <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.65 }}>{String(value ?? '')}</div>;
}

function SelectedTopicDraft({ accountId, topicId, onNavigate }: { accountId: string; topicId: string; onNavigate: (page: Page) => void }) {
  const [context, setContext] = useState<ContentDraftContext | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [titlesText, setTitlesText] = useState('');
  const [mainText, setMainText] = useState('');
  const [hookText, setHookText] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    try { setContext(await fetchOperatorContentDraft(accountId, topicId)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : '草稿读取失败。'); }
  }, [accountId, topicId]);
  useEffect(() => { void load(); }, [load]);

  const runGenerate = async () => {
    setBusy(true); setError('');
    try { setContext(await generateOperatorContentDraft(accountId, topicId)); setEditing(false); }
    catch (reason) { setError(reason instanceof Error ? reason.message : '生成内容草稿失败。'); }
    finally { setBusy(false); }
  };
  const beginEdit = () => {
    const content = context?.draft?.content || {};
    setTitlesText(Array.isArray(content.title_candidates) ? content.title_candidates.join('\n') : '');
    setMainText(context?.account.platform === 'xiaohongshu'
      ? String(content.body_markdown || '')
      : Array.isArray(content.subtitles) ? content.subtitles.join('\n') : '');
    setHookText(String(content.hook || ''));
    setEditing(true);
  };
  const saveEdit = async () => {
    if (!context?.draft) return;
    setBusy(true); setError('');
    const content = { ...context.draft.content,
      title_candidates: titlesText.split('\n').map((item) => item.trim()).filter(Boolean),
      ...(context.account.platform === 'xiaohongshu'
        ? { body_markdown: mainText }
        : { subtitles: mainText.split('\n').map((item) => item.trim()).filter(Boolean), hook: hookText }),
    };
    try { setContext(await updateOperatorContentDraft(accountId, topicId, content)); setEditing(false); }
    catch (reason) { setError(reason instanceof Error ? reason.message : '保存草稿失败。'); }
    finally { setBusy(false); }
  };

  const content = context?.draft?.content;
  return <div className="card" style={{ padding: 12, display: 'grid', gap: 10, borderColor: 'var(--border)' }}>
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
      <div><strong>内容草稿</strong>{context?.draft && <span className="page-subtitle"> · V{context.draft.version} · AI 生成 · 策略 V{context.draft.strategy_version}</span>}</div>
      {!content ? <button className="btn btn-sm btn-primary" disabled={busy} onClick={() => void runGenerate()}>{busy ? '生成中…' : '生成内容草稿'}</button>
        : <div style={{ display: 'flex', gap: 6 }}>
          <button className="btn btn-sm" disabled={busy || editing} onClick={beginEdit}>编辑草稿</button>
          <button className="btn btn-sm" disabled={busy || editing} onClick={() => void runGenerate()}>{busy ? '生成中…' : '重新生成版本'}</button>
        </div>}
    </div>
    <div className="page-subtitle">草稿仅供审核和修改；系统不会自动发布。请自行核实素材与个人经历。</div>
    {error && <div className="page-subtitle" role="alert">{error}</div>}
    {editing && content && <div style={{ display: 'grid', gap: 8 }}>
      <label className="field-label">标题候选（每行一条）<textarea className="input" rows={5} value={titlesText} onChange={(event) => setTitlesText(event.target.value)} /></label>
      {context?.account.platform === 'xiaohongshu'
        ? <label className="field-label">完整正文<textarea className="input" rows={12} value={mainText} onChange={(event) => setMainText(event.target.value)} /></label>
        : <><label className="field-label">Hook<textarea className="input" rows={3} value={hookText} onChange={(event) => setHookText(event.target.value)} /></label>
          <label className="field-label">字幕（每行一条）<textarea className="input" rows={6} value={mainText} onChange={(event) => setMainText(event.target.value)} /></label></>}
      <div style={{ display: 'flex', gap: 8 }}>
        <button className="btn btn-sm btn-primary" disabled={busy} onClick={() => void saveEdit()}>{busy ? '保存中…' : '保存修改'}</button>
        <button className="btn btn-sm" disabled={busy} onClick={() => setEditing(false)}>取消</button>
      </div>
    </div>}
    {!editing && content && <div style={{ display: 'grid', gap: 10 }}>
      {Object.entries(content).map(([key, value]) => <div key={key}>
        <strong>{DRAFT_LABELS[key] || key}</strong>
        <div style={{ marginTop: 3 }}><DraftValue value={value} /></div>
      </div>)}
      <div className="page-subtitle">发布前请补入可核实的真实信息；系统建议的素材不代表你已拥有。</div>
      <button className="btn btn-sm btn-primary" onClick={() => onNavigate('operator-calendar')}>采用这个方案，安排发布时间</button>
    </div>}
    {!content && !error && <div className="page-subtitle">选题已选中。生成后会保存为此选题的独立草稿版本。</div>}
  </div>;
}

function TopicCard({ topic, selectedToday, accountId, onSelect, onNavigate }: {
  topic: DailyTopic; selectedToday: boolean; accountId: string; onSelect: () => void; onNavigate: (page: Page) => void;
}) {
  const label = topic.status === 'SELECTED' ? '已选择' : topic.status === 'RECOMMENDED' ? '今日主推' : '备选';
  return (
    <article className={`card ${topic.status === 'RECOMMENDED' ? 'card-hover' : ''}`} style={{ padding: 14, display: 'grid', gap: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
        <span className="badge">{label}</span>
        <strong style={{ fontSize: 14 }}>推荐排序 {topic.score} / 100</strong>
      </div>
      <h3 style={{ margin: 0, lineHeight: 1.4 }}>{topic.title}</h3>
      <div className="page-subtitle"><strong>对应方向：</strong>{topic.pillar_name || topic.pillar_id}</div>
      <div><strong>拍摄角度：</strong>{topic.angle}</div>
      <div>{topic.description}</div>
      {topic.historical_evidence.length > 0 ? <details className="page-subtitle">
        <summary style={{ cursor: 'pointer' }}>为什么推荐</summary>
        <div style={{ marginTop: 6 }}>
        <div>{topic.recommendation_reason}</div>
        <strong>历史依据：</strong>{topic.historical_evidence.map((item) => {
          const group = String(item.group || '分组');
          const sample = item.sample_size == null ? '—' : String(item.sample_size);
          const views = item.views_median == null ? '—' : String(item.views_median);
          const engagement = typeof item.engagement_rate_median === 'number'
            ? `${(item.engagement_rate_median * 100).toFixed(2)}%` : '—';
          return `${group} · ${sample} 条历史作品，播放中位数 ${views}，互动率 ${engagement}`;
        }).join('；')}（仅作历史描述，不代表因果）
        </div>
      </details> : <details className="page-subtitle"><summary style={{ cursor: 'pointer' }}>为什么推荐</summary><div style={{ marginTop: 6 }}>{topic.recommendation_reason}</div><div>当前没有历史表现样本；此建议基于已确认定位进行首阶段实验。</div></details>}
      <div><strong>实验目标：</strong>{topic.experiment_question}</div>
      <div className="page-subtitle"><strong>制作难度：</strong>{DIFFICULTY[topic.production_difficulty]}</div>
      <div><strong>所需素材：</strong>{topic.material_requirements.join('、') || '按真实场景拍摄/记录'}</div>
      <details>
        <summary style={{ cursor: 'pointer' }}>查看排序说明</summary>
        <div className="page-subtitle" style={{ marginTop: 8 }}>{topic.score_breakdown.note}</div>
      </details>
      {topic.status !== 'SELECTED' && <button className="btn btn-sm" disabled={selectedToday}
        onClick={onSelect}>{selectedToday ? '今天已选择一个选题' : '选择这个选题'}</button>}
      {topic.status === 'SELECTED' && <SelectedTopicDraft accountId={accountId} topicId={topic.id} onNavigate={onNavigate} />}
    </article>
  );
}

function AccountOperations({ account, onNavigate }: { account: OperatorAccount; onNavigate: (page: Page) => void }) {
  const [state, setState] = useState<DailyTopicAccountState | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [publishedThisWeek, setPublishedThisWeek] = useState<FeedbackPost[]>([]);
  const [todayPlanCount, setTodayPlanCount] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const daily = await fetchDailyTopics(account.id);
      setState(daily);
      if (daily.local_date) {
        const start = new Date(`${daily.local_date}T00:00:00`);
        start.setDate(start.getDate() - 6);
        const weekStart = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`;
        const [feedback, calendar] = await Promise.all([
          fetchFeedbackContext(account.id), fetchOperatorCalendar(account.id, daily.local_date, daily.local_date),
        ]);
        setPublishedThisWeek(feedback.published_posts.filter((post) => post.published_at.slice(0, 10) >= weekStart && post.published_at.slice(0, 10) <= daily.local_date));
        setTodayPlanCount(calendar.calendar_items.filter((item) => item.status !== 'CANCELLED').length);
      }
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : '今日运营数据加载失败。'); }
    finally { setLoading(false); }
  }, [account.id]);

  useEffect(() => { void load(); }, [load]);

  const generate = async () => {
    setBusy(true); setError('');
    try {
      const batch = await generateDailyTopics(account.id);
      setState((current) => current ? { ...current, today: batch, generation_mode: batch.generation_mode } : current);
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : '生成失败。'); }
    finally { setBusy(false); }
  };

  const select = async (topicId: string) => {
    setBusy(true); setError('');
    try {
      const batch = await selectDailyTopic(account.id, topicId);
      setState((current) => current ? { ...current, today: batch } : current);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '选择失败。'); }
    finally { setBusy(false); }
  };

  const batch = state?.today;
  const selectedToday = !!batch?.topics.some((topic) => topic.status === 'SELECTED');
  return (
    <section className="card" style={{ padding: 16, display: 'grid', gap: 12 }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h2 style={{ margin: 0 }}>{account.name}</h2>
          <div className="page-subtitle" style={{ marginTop: 4 }}>
            {account.platform === 'douyin' ? '抖音' : '小红书'} · {state?.local_date || '今日'}
            {state?.strategy_version ? ` · 策略 V${state.strategy_version}` : ''}
            {state?.confidence === 'LOW' ? ' · 当前策略仍处于实验验证期' : ''}
          </div>
        </div>
        {state?.can_generate && <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {batch?.generation_mode && <span className="badge">{batch.generation_mode === 'AI' ? 'AI 生成' : '本地模板兜底'}</span>}
          <button className="btn btn-sm btn-primary" disabled={busy || loading || selectedToday} onClick={generate}>
            {busy ? '处理中…' : batch ? '换一批' : '生成今日选题'}
          </button>
        </div>}
      </header>
      {state?.can_generate && <div className="page-subtitle">
        {state.platform === 'xiaohongshu'
          ? '当前建议主要依据账号定位，尚无历史表现数据。'
          : state.historical_sample_size != null ? `参考 ${state.historical_sample_size} 条有效历史作品；` : '当前属于定位假设驱动的第一阶段实验；'}
        主推一条、另有两个备选。评分用于排序，不是成功概率。
      </div>}
      {state?.allocation_plan && <div className="card" style={{ padding: 12, display: 'grid', gap: 6 }}>
        <strong>本周内容方向进度</strong>
        {!publishedThisWeek.length && <div className="page-subtitle">本周还没有已发布作品；发布后会按真实作品更新进度。</div>}
        {state.allocation_plan.map((item) => {
          const actual = publishedThisWeek.filter((post) => post.pillar_id === item.pillar_id).length;
          const total = publishedThisWeek.length;
          const percent = total ? Math.round(actual / total * 100) : null;
          return <div className="page-subtitle" key={item.pillar_id}>{item.pillar_name}：目标 {item.target_percent}% · 本周实际 {percent == null ? '—' : `${percent}% (${actual}/${total})`}</div>;
        })}
        <div className="page-subtitle">进度只统计本周真实登记的发布作品，不按生成或选择的选题计数。</div>
      </div>}
      {state && <div className="page-subtitle">今日计划：{todayPlanCount ? `已有 ${todayPlanCount} 条` : '还没有计划'} · <button className="btn btn-sm" onClick={() => onNavigate('operator-calendar')}>打开运营日历</button></div>}
      {state && !state.can_generate && <div className="card" style={{ padding: 14 }}>
        <strong>尚未确认运营策略。</strong>
        <div className="page-subtitle" style={{ marginTop: 4 }}>{state.gate_reason || '暂不能生成正式选题。'}</div>
        <button className="btn btn-sm" style={{ marginTop: 10 }} onClick={() => onNavigate('accounts')}>前往账号页查看策略</button>
      </div>}
      {loading && <div className="page-subtitle">正在加载今日选题…</div>}
      {error && <div className="page-subtitle" role="alert">{error}</div>}
      {state?.can_generate && !batch && !loading && <div className="page-subtitle">今天还没有候选选题，点击“生成今日选题”。</div>}
      {batch && <div style={{ display: 'grid', gap: 10 }}>
        {batch.topics.map((topic) => (
          <TopicCard key={topic.id} topic={topic} accountId={account.id} selectedToday={selectedToday}
            onSelect={() => void select(topic.id)} onNavigate={onNavigate} />
        ))}
      </div>}
    </section>
  );
}

export default function DailyOperationsPanel({ onNavigate }: Props) {
  const [accounts, setAccounts] = useState<OperatorAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    fetchOperatorAccounts().then(setAccounts)
      .catch((reason) => setError(reason instanceof Error ? reason.message : '账号加载失败。'))
      .finally(() => setLoading(false));
  }, []);

  return <div style={{ display: 'grid', gap: 12 }}>
    {loading && <div className="card page-subtitle" style={{ padding: 16 }}>正在加载运营账号…</div>}
    {error && <div className="card page-subtitle" style={{ padding: 16 }} role="alert">{error}</div>}
    {!loading && accounts.map((account) => <AccountOperations key={account.id} account={account} onNavigate={onNavigate} />)}
  </div>;
}
