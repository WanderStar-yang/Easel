import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  cancelOperatorPlan, fetchOperatorAccounts, fetchOperatorCalendar, markOperatorPlanPublished,
  markOperatorPlanReady, rescheduleOperatorTopic, scheduleOperatorTopic,
} from '../lib/api';
import type { OperatorAccount, OperatorCalendarContext, OperatorCalendarItem } from '../lib/api';

const STATUS_LABEL: Record<OperatorCalendarItem['status'], string> = {
  SELECTED: '已选题', DRAFT: '有草稿', READY: '待发布', PUBLISHED: '已发布',
  REVIEWED: '已复盘', CANCELLED: '已取消',
};

function dateKey(value: Date): string {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
}

function localInput(value: string | Date): string {
  const date = typeof value === 'string' ? new Date(value) : value;
  const pad = (part: number) => String(part).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function localDateTime(value: string): string {
  return new Date(value).toISOString();
}

function currentMonth(): Date {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), 1);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '操作失败，请稍后重试。';
}

export default function OperatorCalendarPage() {
  const [accounts, setAccounts] = useState<OperatorAccount[]>([]);
  const [accountId, setAccountId] = useState('');
  const [context, setContext] = useState<OperatorCalendarContext | null>(null);
  const [month, setMonth] = useState(currentMonth);
  const [topicId, setTopicId] = useState('');
  const [plannedAt, setPlannedAt] = useState(() => localInput(new Date()));
  const [reschedule, setReschedule] = useState<Record<string, string>>({});
  const [publishing, setPublishing] = useState<OperatorCalendarItem | null>(null);
  const [publishForm, setPublishForm] = useState({ title: '', published_at: localInput(new Date()), published_url: '', platform_post_id: '', content_source: 'UNKNOWN', hook_type: '', duration_seconds: '' });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const firstDay = new Date(month.getFullYear(), month.getMonth(), 1);
  const lastDay = new Date(month.getFullYear(), month.getMonth() + 1, 0);
  const rangeStart = dateKey(firstDay);
  const rangeEnd = dateKey(lastDay);

  const refresh = useCallback(async (id: string, start: string, end: string) => {
    if (!id) return;
    setLoading(true); setError('');
    try {
      const value = await fetchOperatorCalendar(id, start, end);
      setContext(value);
      setTopicId((current) => current || value.selected_topics[0]?.id || '');
      setReschedule((current) => {
        const next = { ...current };
        for (const item of value.calendar_items) next[item.id] ||= localInput(item.planned_publish_at);
        return next;
      });
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    fetchOperatorAccounts().then((items) => {
      setAccounts(items);
      const first = items.find((item) => item.status === 'ACTIVE') || items[0];
      if (first) setAccountId(first.id); else setLoading(false);
    }).catch((reason: unknown) => { setError(errorMessage(reason)); setLoading(false); });
  }, []);
  useEffect(() => { if (accountId) void refresh(accountId, rangeStart, rangeEnd); }, [accountId, rangeStart, rangeEnd, refresh]);

  const cells = useMemo(() => {
    const start = new Date(month.getFullYear(), month.getMonth(), 1);
    start.setDate(1 - ((start.getDay() + 6) % 7));
    return Array.from({ length: 42 }, (_, index) => {
      const value = new Date(start); value.setDate(start.getDate() + index); return value;
    });
  }, [month]);
  const itemsByDate = useMemo(() => {
    const result: Record<string, OperatorCalendarItem[]> = {};
    for (const item of context?.calendar_items || []) {
      const key = item.planned_publish_at.slice(0, 10);
      (result[key] ||= []).push(item);
    }
    return result;
  }, [context]);
  const selectedTopic = context?.selected_topics.find((item) => item.id === topicId);

  const runAction = async (action: () => Promise<unknown>, message: string) => {
    setBusy(true); setError(''); setNotice('');
    try { await action(); setNotice(message); await refresh(accountId, rangeStart, rangeEnd); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  };

  const schedule = () => {
    if (!selectedTopic) { setError('当前策略下没有可安排的已选择选题。'); return; }
    void runAction(() => scheduleOperatorTopic(accountId, {
      topic_id: selectedTopic.id, draft_id: selectedTopic.draft_id, planned_publish_at: localDateTime(plannedAt),
    }), '选题已加入账号运营日历。');
  };

  const openPublish = (item: OperatorCalendarItem) => {
    setPublishing(item);
    setPublishForm({ title: item.topic_title, published_at: localInput(new Date()), published_url: '', platform_post_id: '', content_source: 'UNKNOWN', hook_type: '', duration_seconds: '' });
  };

  const savePublication = () => {
    if (!publishing) return;
    void runAction(() => markOperatorPlanPublished(accountId, publishing.id, {
      ...publishForm, title: publishForm.title.trim(), published_at: localDateTime(publishForm.published_at),
      published_url: publishForm.published_url.trim() || null, hook_type: publishForm.hook_type.trim() || null,
      duration_seconds: publishForm.duration_seconds ? Number(publishForm.duration_seconds) : null,
    }), '已保存实际发布记录。平台数据可在“周复盘”页面继续录入。').then(() => setPublishing(null));
  };

  const shiftMonth = (delta: number) => setMonth((value) => new Date(value.getFullYear(), value.getMonth() + delta, 1));

  return <div className="page" style={{ display: 'grid', gap: 16, maxWidth: 1180 }}>
    <header>
      <h1 style={{ marginBottom: 4 }}>运营日历</h1>
      <div className="page-subtitle">安排已选择的选题、准备发布，并在你手动发布后登记实际结果。Easel 不会自动发布内容。</div>
    </header>

    <section className="card" style={{ display: 'flex', alignItems: 'end', flexWrap: 'wrap', gap: 10, padding: 14 }}>
      <label className="field-label">运营账号<select className="input" value={accountId} onChange={(event) => { setContext(null); setTopicId(''); setAccountId(event.target.value); }}>
        {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
      </select></label>
      <button className="btn btn-sm" disabled={busy} onClick={() => shiftMonth(-1)}>上个月</button>
      <strong>{month.getFullYear()} 年 {month.getMonth() + 1} 月</strong>
      <button className="btn btn-sm" disabled={busy} onClick={() => shiftMonth(1)}>下个月</button>
    </section>

    {error && <div className="card" role="alert" style={{ padding: 12, color: 'var(--red)' }}>{error}</div>}
    {notice && <div className="card" role="status" style={{ padding: 12 }}>{notice}</div>}
    {loading && <div className="page-subtitle">正在读取账号日历…</div>}

    {context && <>
      <section className="card" style={{ display: 'grid', gap: 10, padding: 14 }}>
        <div><h2 style={{ margin: 0 }}>安排选题</h2><div className="page-subtitle">仅显示当前 ACTIVE Strategy 下已选择的选题；草稿会绑定当前版本。</div></div>
        {!context.selected_topics.length ? <div className="page-subtitle">当前没有可安排的已选择选题。先在“今日运营”中选择一个候选选题。</div> : <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'end' }}>
          <label className="field-label" style={{ minWidth: 260 }}>已选择选题<select className="input" value={topicId} onChange={(event) => setTopicId(event.target.value)}>
            {context.selected_topics.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.pillar_name}</option>)}
          </select></label>
          <label className="field-label">计划发布时间<input className="input" type="datetime-local" value={plannedAt} onChange={(event) => setPlannedAt(event.target.value)} /></label>
          <button className="btn btn-primary" disabled={busy || !selectedTopic} onClick={schedule}>加入日历</button>
        </div>}
      </section>

      <section className="card" style={{ padding: 12 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, minmax(0, 1fr))', gap: 4, marginBottom: 6 }}>
          {['一', '二', '三', '四', '五', '六', '日'].map((day) => <div key={day} className="page-subtitle" style={{ textAlign: 'center', padding: 5 }}>周{day}</div>)}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, minmax(0, 1fr))', gap: 4 }}>
          {cells.map((cell, index) => {
            const key = dateKey(cell);
            const inMonth = cell.getMonth() === month.getMonth();
            const items = itemsByDate[key] || [];
            return <div key={`${key}-${index}`} style={{ minHeight: 86, border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 6, opacity: inMonth ? 1 : 0.5, background: 'var(--surface)' }}>
              <div className="page-subtitle" style={{ fontWeight: 600 }}>{cell.getDate()}</div>
              {items.slice(0, 2).map((item) => <div key={item.id} title={`${STATUS_LABEL[item.status]} · ${item.topic_title}`} style={{ marginTop: 4, padding: '3px 5px', borderRadius: 5, background: 'var(--layer-plan)', fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {STATUS_LABEL[item.status]} · {item.topic_title}
              </div>)}
              {items.length > 2 && <div className="page-subtitle">+{items.length - 2} 条</div>}
            </div>;
          })}
        </div>
      </section>

      <section style={{ display: 'grid', gap: 10 }}>
        <h2 style={{ margin: 0 }}>本月计划 · {context.calendar_items.length} 条</h2>
        {!context.calendar_items.length && <div className="card page-subtitle" style={{ padding: 14 }}>本月暂无运营计划。选择已确认选题和计划时间后加入日历。</div>}
        {context.calendar_items.map((item) => <article key={item.id} className="card" style={{ padding: 12, display: 'grid', gap: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
            <strong>{item.topic_title}</strong><span className="page-subtitle">{STATUS_LABEL[item.status]}{item.strategy_is_current === false && ['SELECTED', 'DRAFT', 'READY'].includes(item.status) ? ' · 旧策略计划' : ''} · {item.pillar_name || '未关联方向'} · {item.platform === 'douyin' ? '抖音' : '小红书'} · Strategy V{item.strategy_version}{item.draft_version ? ` · 草稿 V${item.draft_version}` : ''}</span>
          </div>
          {item.status === 'PUBLISHED' || item.status === 'REVIEWED' ? <div className="page-subtitle">实际发布时间：{item.actual_publish_at} · {item.published_url ? <a href={item.published_url} target="_blank" rel="noreferrer">查看已发布作品</a> : '未填写作品链接'}{item.review_id ? ' · 已进入周复盘' : ''}</div> : <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'end', gap: 8 }}>
            {item.status !== 'CANCELLED' && <label className="field-label">计划时间<input className="input" type="datetime-local" disabled={item.strategy_is_current === false} value={reschedule[item.id] || localInput(item.planned_publish_at)} onChange={(event) => setReschedule((current) => ({ ...current, [item.id]: event.target.value }))} /></label>}
            {item.status !== 'CANCELLED' && <button className="btn btn-sm" disabled={busy || item.strategy_is_current === false} onClick={() => void runAction(
              () => rescheduleOperatorTopic(accountId, item.id, localDateTime(reschedule[item.id] || localInput(item.planned_publish_at))), '计划时间已更新。')}>调整时间</button>}
            {['SELECTED', 'DRAFT'].includes(item.status) && <button className="btn btn-sm btn-primary" disabled={busy || item.strategy_is_current === false} onClick={() => void runAction(() => markOperatorPlanReady(accountId, item.id), '计划已标为待发布。')}>标为待发布</button>}
            {item.status === 'READY' && <button className="btn btn-sm btn-primary" disabled={busy || item.strategy_is_current === false} onClick={() => openPublish(item)}>登记已发布</button>}
            {['SELECTED', 'DRAFT', 'READY'].includes(item.status) && <button className="btn btn-sm" disabled={busy} onClick={() => void runAction(() => cancelOperatorPlan(accountId, item.id), '计划已取消。')}>取消计划</button>}
            {item.strategy_is_current === false && item.status !== 'CANCELLED' && <span className="page-subtitle">策略已更新；请取消此计划并按当前策略重新安排。</span>}
            {item.status === 'CANCELLED' && <span className="page-subtitle">可从当前选题重新安排新计划。</span>}
          </div>}
        </article>)}
      </section>

      {publishing && <section className="card" style={{ padding: 14, display: 'grid', gap: 10 }}>
        <div><h2 style={{ margin: 0 }}>登记实际发布</h2><div className="page-subtitle">这是实际发布结果记录，不会调用抖音或小红书发布接口。</div></div>
        <strong>{publishing.topic_title}</strong>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
          <label className="field-label">实际标题<input className="input" value={publishForm.title} onChange={(event) => setPublishForm({ ...publishForm, title: event.target.value })} /></label>
          <label className="field-label">实际发布时间<input className="input" type="datetime-local" value={publishForm.published_at} onChange={(event) => setPublishForm({ ...publishForm, published_at: event.target.value })} /></label>
          <label className="field-label">内容来源<select className="input" value={publishForm.content_source} onChange={(event) => setPublishForm({ ...publishForm, content_source: event.target.value })}>
            <option value="UNKNOWN">无法判断</option><option value="REAL">真实拍摄</option><option value="AI">AI 生成</option><option value="MIXED">真人/AI 混合</option>
          </select></label>
          <label className="field-label">作品链接（可选）<input className="input" value={publishForm.published_url} onChange={(event) => setPublishForm({ ...publishForm, published_url: event.target.value })} /></label>
          <label className="field-label">平台作品 ID（可选）<input className="input" value={publishForm.platform_post_id} onChange={(event) => setPublishForm({ ...publishForm, platform_post_id: event.target.value })} /></label>
          <label className="field-label">Hook 类型（可选）<input className="input" value={publishForm.hook_type} onChange={(event) => setPublishForm({ ...publishForm, hook_type: event.target.value })} /></label>
          <label className="field-label">视频时长（秒，可选）<input className="input" type="number" min="1" value={publishForm.duration_seconds} onChange={(event) => setPublishForm({ ...publishForm, duration_seconds: event.target.value })} /></label>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" disabled={busy || !publishForm.title.trim()} onClick={savePublication}>保存真实发布记录</button>
          <button className="btn" disabled={busy} onClick={() => setPublishing(null)}>稍后登记</button>
        </div>
      </section>}
    </>}
  </div>;
}
