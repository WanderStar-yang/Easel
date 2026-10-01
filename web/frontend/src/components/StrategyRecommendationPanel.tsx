import { useCallback, useEffect, useMemo, useState } from 'react';
import { confirmOperatorStrategy, fetchActiveStrategy, fetchStrategyRecommendation,
  fetchStrategyRecommendationHistory, generateStrategyRecommendation } from '../lib/api';
import type { ActiveStrategy, StrategyRecommendation, OperatorAccount } from '../lib/api';

const LEVEL: Record<string, string> = { SUPPORTED: '有历史样本支持', EXPERIMENTAL: '初步数据，需验证', INSUFFICIENT_DATA: '数据不足' };
const dim: Record<string, string> = { subjects: '出镜主体', content_type: '内容类型', content_source: '内容来源' };
function activeEvidenceSummary(evidence: Record<string, unknown>): string {
  const dimension = dim[String(evidence.dimension)] || String(evidence.source || '历史证据');
  const group = evidence.group ? ` ${String(evidence.group)}` : '';
  const sample = typeof evidence.sample_size === 'number' ? `，样本 ${evidence.sample_size} 条` : '';
  const views = typeof evidence.views_median === 'number' ? `，播放中位数 ${evidence.views_median}` : '';
  const engagement = typeof evidence.engagement_rate_median === 'number'
    ? `，互动率中位数 ${(evidence.engagement_rate_median * 100).toFixed(2)}%` : '';
  const difference = evidence.baseline_difference as { views?: { relative_change?: number | null } } | undefined;
  const relative = typeof difference?.views?.relative_change === 'number'
    ? `，相对整体播放 ${difference.views.relative_change >= 0 ? '+' : ''}${(difference.views.relative_change * 100).toFixed(0)}%` : '';
  return `${dimension}${group}${sample}${views}${relative}${engagement}`;
}

export default function StrategyRecommendationPanel({ account, onClose, onActivated }: {
  account: OperatorAccount; onClose: () => void; onActivated?: () => void;
}) {
  const [item, setItem] = useState<StrategyRecommendation | null>(null);
  const [history, setHistory] = useState<StrategyRecommendation[]>([]);
  const [active, setActive] = useState<ActiveStrategy | null>(null);
  const [editing, setEditing] = useState(false);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [draftPositioning, setDraftPositioning] = useState('');
  const [draftPillars, setDraftPillars] = useState<Array<{
    recommendation_pillar_id: string; name: string; description: string; allocation_ratio: number;
  }>>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const [latest, versions, currentActive] = await Promise.all([
        fetchStrategyRecommendation(account.id), fetchStrategyRecommendationHistory(account.id), fetchActiveStrategy(account.id),
      ]);
      setItem(latest); setHistory(versions); setActive(currentActive);
    } catch { setError('加载策略建议失败，请重试。'); }
  }, [account.id]);
  useEffect(() => { void load(); }, [load]);

  const recommendation = item?.recommendation;

  const generate = async () => {
    setBusy(true); setError('');
    try { await generateStrategyRecommendation(account.id); await load(); }
    catch (err) { setError(err instanceof Error ? err.message : '生成策略建议失败。'); }
    finally { setBusy(false); }
  };

  const beginEditing = () => {
    if (!item?.recommendation || item.status !== 'CURRENT' || active) return;
    setDraftPositioning(item.recommendation.positioning_hypothesis.summary);
    setDraftPillars(item.recommendation.pillars.map((pillar) => ({
      recommendation_pillar_id: pillar.id, name: pillar.name, description: pillar.description,
      allocation_ratio: pillar.initial_test_allocation,
    })));
    setEditing(true); setSummaryOpen(false); setError('');
  };

  const ratioTotal = draftPillars.reduce((total, pillar) => total + (Number(pillar.allocation_ratio) || 0), 0);
  const experimentQuestions = useMemo(() => {
    if (!recommendation) return [];
    const byId = new Map(recommendation.evidence.map((evidence) => [String(evidence.id), evidence]));
    return recommendation.pillars.map((pillar) => {
      const groups = pillar.evidence_ids.map((id) => String(byId.get(id)?.group || '')).filter(Boolean);
      if (groups.includes('缅因')) return { pillar_name: pillar.name, question: '缅因相关内容较高的历史播放表现，未来四周能否持续？' };
      if (groups.includes('双猫')) return { pillar_name: pillar.name, question: '双猫互动内容能否在未来四周持续获得高于整体基准的互动率？' };
      if (groups.includes('搞笑/趣味') || pillar.name.includes('趣味')) return {
        pillar_name: pillar.name, question: '趣味内容较高播放、偏低互动的现象是否稳定，并观察有数据时的涨粉表现。',
      };
      return { pillar_name: pillar.name, question: pillar.experiment_question };
    });
  }, [recommendation]);

  const confirm = async () => {
    if (!item || ratioTotal !== 100) return;
    setBusy(true); setError('');
    try {
      const created = await confirmOperatorStrategy(account.id, {
        recommendation_id: item.id, positioning: draftPositioning, pillars: draftPillars,
      });
      setActive(created); setEditing(false); setSummaryOpen(false); await load(); onActivated?.();
    } catch (err) { setError(err instanceof Error ? err.message : '确认策略失败，请重试。'); }
    finally { setBusy(false); }
  };

  const evidenceById = new Map((recommendation?.evidence || []).map((e) => [String(e.id), e]));
  return <section className="card" style={{ marginTop: 16, padding: 18 }} aria-label={`${account.name}策略建议`}>
    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
      <div><h2 style={{ margin: 0, fontSize: 19 }}>策略建议</h2>
        <p className="page-subtitle" style={{ margin: '5px 0 0' }}>基于历史表现和账号资料整理的初始实验方向，不会自动启用。</p></div>
      <button className="btn btn-sm" onClick={onClose}>收起</button>
    </div>
    {error && <div role="alert" style={{ color: 'var(--red)', marginTop: 12 }}>{error}</div>}
    {item && recommendation && <div style={{ marginTop: 14 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
        <span className={`badge ${item.status === 'CURRENT' ? 'badge-ok' : ''}`}>建议 V{item.version} · {item.status === 'CURRENT' ? '当前版本' : item.status === 'STALE' ? '依据已过期' : '历史版本'}</span>
        <span className="badge">策略可信度：{recommendation.confidence === 'LOW' ? '较低' : recommendation.confidence === 'MEDIUM' ? '中等' : '较高'}</span>
        {recommendation.source.baseline_version && <span className="badge">历史基准 V{recommendation.source.baseline_version}</span>}
        <span className="badge">有效历史作品 {recommendation.source.canonical_sample_size} 条</span>
      </div>
      <p className="page-subtitle">{recommendation.confidence_note}</p>
      {recommendation.source.canonical_sample_size === 0 && <div className="card" style={{ padding: 12, marginTop: 10 }}>
        当前没有历史数据，这份策略主要基于账号定位假设。你仍可以主动确认它，作为起步实验方案。
      </div>}
      {recommendation.confidence === 'LOW' && <div className="card" style={{ padding: 12, marginTop: 10 }}>
        当前历史数据仍有部分分类缺失；以下策略是第一阶段测试方案，不是永久运营规则。未来将根据真实发布结果持续调整。
        {recommendation.evidence_sufficiency && <div style={{ marginTop: 5 }}>
          出镜主体仍有 {recommendation.evidence_sufficiency.unknown_count} 条无法可靠分类
          （{Math.round(recommendation.evidence_sufficiency.unknown_count / Math.max(1, recommendation.source.canonical_sample_size) * 100)}%）。
        </div>}
      </div>}
      {recommendation.evidence_sufficiency && <div className="card" style={{ padding: 12, marginTop: 10 }}>
        <strong>主体证据充分性</strong>
        <div className="page-subtitle" style={{ marginTop: 5 }}>
          主体覆盖 {Math.round(recommendation.evidence_sufficiency.subjects_coverage * 100)}% · 未分类 {recommendation.evidence_sufficiency.unknown_count} 条 ·
          缅因 {recommendation.evidence_sufficiency.major_group_sample_sizes['缅因'] ?? 0} 条 ·
          布偶 {recommendation.evidence_sufficiency.major_group_sample_sizes['布偶'] ?? 0} 条 ·
          双猫 {recommendation.evidence_sufficiency.major_group_sample_sizes['双猫'] ?? 0} 条
        </div>
        <div className="page-subtitle" style={{ marginTop: 4 }}>{recommendation.evidence_sufficiency.note}</div>
      </div>}
      <div className="card" style={{ padding: 12, marginTop: 10 }}>
        <div><strong>定位假设：</strong>{recommendation.positioning_hypothesis.summary}</div>
        <div className="page-subtitle">{recommendation.positioning_hypothesis.note}</div>
        <div style={{ marginTop: 8 }}><strong>受众兴趣假设：</strong>{recommendation.audience_hypothesis.summary}</div>
        <div className="page-subtitle">{recommendation.audience_hypothesis.note}</div>
      </div>
      {recommendation.problem_observations.length > 0 && <div style={{ marginTop: 12 }}>
        <strong>当前数据限制</strong>
        {recommendation.problem_observations.map((line) => <div className="page-subtitle" key={line} style={{ marginTop: 4 }}>{line}</div>)}
      </div>}
      {recommendation.opportunity_directions.length > 0 && <div style={{ marginTop: 12 }}>
        <strong>可继续验证的历史分组</strong>
        <div className="page-subtitle" style={{ marginTop: 4 }}>{recommendation.opportunity_directions.map((item) =>
          `${dim[item.dimension] || item.dimension} ${item.group}（${item.sample_size} 条，${LEVEL[item.evidence_level]}）`).join('；')}
        </div>
      </div>}
      <h3 style={{ margin: '18px 0 8px', fontSize: 16 }}>建议测试的内容支柱</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 9 }}>
        {recommendation.pillars.map((pillar) => <article className="card" key={pillar.id} style={{ padding: 13 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
            <strong>{pillar.name}</strong><span className="badge">{pillar.initial_test_allocation}% 测试分配</span>
          </div>
          <div className="page-subtitle" style={{ marginTop: 5 }}>{LEVEL[pillar.evidence_level]}</div>
          <p style={{ fontSize: 13, lineHeight: 1.6, margin: '8px 0' }}>{pillar.description}</p>
          {pillar.why && <div style={{ fontSize: 13, lineHeight: 1.6 }}><strong>为什么：</strong>{pillar.why}</div>}
          <div style={{ fontSize: 13 }}><strong>验证目标：</strong>{pillar.goal}</div>
          <div style={{ fontSize: 13, marginTop: 6 }}><strong>四周实验问题：</strong>{pillar.experiment_question}</div>
          {pillar.evidence_ids.length > 0 && <div className="page-subtitle" style={{ marginTop: 8 }}>
            数据依据：{pillar.evidence_ids.map((id) => {
              const e = evidenceById.get(id);
              return e ? `${dim[String(e.dimension)] || e.source} ${String(e.group || '')}（样本 ${String(e.sample_size)} 条，播放中位数 ${typeof e.views_median === 'number' ? e.views_median : '暂无'}${typeof e.baseline_difference?.views?.relative_change === 'number' ? `，相对整体 ${e.baseline_difference.views.relative_change >= 0 ? '+' : ''}${(e.baseline_difference.views.relative_change * 100).toFixed(0)}%` : ''}${typeof e.engagement_rate_median === 'number' ? `，互动率中位数 ${(e.engagement_rate_median * 100).toFixed(2)}%` : ''}，${LEVEL[String(e.level)] || e.level}）` : id;
            }).join('；')}
          </div>}
          {pillar.allocation_reason?.summary && <div className="page-subtitle" style={{ marginTop: 8 }}>
            比例依据：{pillar.allocation_reason.summary}
          </div>}
        </article>)}
      </div>
      <p className="page-subtitle" style={{ marginTop: 12 }}>四周周期；比例代表初始测试资源分配，不是固定发布配比。历史差异是描述性观察，不代表因果。</p>
      {recommendation.limitations.map((line) => <p className="page-subtitle" key={line} style={{ margin: '4px 0' }}>· {line}</p>)}
      <details style={{ marginTop: 12 }}><summary style={{ cursor: 'pointer' }}>查看数据依据</summary>
        <div style={{ display: 'grid', gap: 6, marginTop: 8 }}>
          {recommendation.evidence.map((e) => <div className="card" key={String(e.id)} style={{ padding: 10, fontSize: 13 }}>
            <strong>{String(e.group || e.source)}</strong> · {LEVEL[String(e.level)] || String(e.level)} · 样本 {String(e.sample_size ?? '—')} 条
            {typeof e.views_median === 'number' && <span> · 播放中位数 {e.views_median}</span>}
            {typeof e.views_p25 === 'number' && typeof e.views_p75 === 'number' && <span> · 播放 P25–P75 {e.views_p25}–{e.views_p75}</span>}
            {typeof e.engagement_rate_median === 'number' && <span> · 互动率中位数 {(e.engagement_rate_median * 100).toFixed(2)}%</span>}
            {typeof e.engagement_rate_p25 === 'number' && typeof e.engagement_rate_p75 === 'number' && <span> · 互动率 P25–P75 {(e.engagement_rate_p25 * 100).toFixed(2)}%–{(e.engagement_rate_p75 * 100).toFixed(2)}%</span>}
            {typeof e.baseline_difference?.views?.relative_change === 'number' && <span> · 相对整体播放 {e.baseline_difference.views.relative_change >= 0 ? '+' : ''}{(e.baseline_difference.views.relative_change * 100).toFixed(0)}%</span>}
            {typeof e.baseline_difference?.engagement_rate?.relative_change === 'number' && <span> · 相对整体互动率 {e.baseline_difference.engagement_rate.relative_change >= 0 ? '+' : ''}{(e.baseline_difference.engagement_rate.relative_change * 100).toFixed(0)}%</span>}
            <div className="page-subtitle">{String(e.note || '')}</div>
          </div>)}
        </div>
      </details>
    </div>}
    {!item && <p className="page-subtitle" style={{ marginTop: 14 }}>尚未生成策略建议。系统会先检查当前历史基准和诊断状态。</p>}
    {active && <div className="card" style={{ marginTop: 14, padding: 14 }}>
      <h3 style={{ margin: '0 0 6px' }}>第一阶段运营策略已启用</h3>
      <div>策略 V{active.version} · {new Date(active.confirmed_at).toLocaleString()} · 测试周期：未来 {active.experiment_plan.horizon_weeks} 周</div>
      <div style={{ marginTop: 8 }}><strong>当前定位：</strong>{active.positioning}</div>
      <div className="page-subtitle" style={{ marginTop: 4 }}>策略可信度：{active.confidence_at_confirmation === 'LOW' ? '较低' : active.confidence_at_confirmation === 'MEDIUM' ? '中等' : '较高'}。该策略将在后续真实数据复盘中持续调整。</div>
      <div style={{ display: 'grid', gap: 7, marginTop: 10 }}>
        {active.pillars.map((pillar) => <div key={pillar.id}>
          <strong>{pillar.name} {pillar.allocation_ratio}%</strong>
          <div className="page-subtitle">{pillar.description}</div>
          {pillar.evidence_summary.length > 0 && <div className="page-subtitle">历史依据：{pillar.evidence_summary.map(activeEvidenceSummary).join('；')}</div>}
        </div>)}
      </div>
      <h4 style={{ margin: '14px 0 5px' }}>未来四周重点验证</h4>
      {active.experiment_plan.tests.map((test) => <div className="page-subtitle" key={test.pillar_name} style={{ marginTop: 4 }}>· {test.question}</div>)}
      <button className="btn btn-sm" disabled style={{ marginTop: 12 }}>下一步：开始选题规划</button>
      <div className="page-subtitle">选题规划将在下一阶段启用。</div>
    </div>}
    {item && recommendation && item.status === 'CURRENT' && !active && <div style={{ marginTop: 14 }}>
      {!editing && <button className="btn btn-sm btn-primary" onClick={beginEditing}>调整并确认第一阶段策略</button>}
      {editing && <div className="card" style={{ padding: 14 }}>
        <h3 style={{ margin: '0 0 8px' }}>第一阶段运营策略</h3>
        <label style={{ display: 'block', fontSize: 13, marginBottom: 10 }}>推荐定位
          <input className="input" value={draftPositioning} maxLength={240}
            onChange={(event) => setDraftPositioning(event.target.value)} style={{ width: '100%', marginTop: 4 }} />
        </label>
        <div style={{ display: 'grid', gap: 10 }}>
          {draftPillars.map((pillar, index) => <article className="card" key={pillar.recommendation_pillar_id} style={{ padding: 12 }}>
            <label style={{ display: 'block', fontSize: 13 }}>内容方向名称
              <input className="input" value={pillar.name} maxLength={80} onChange={(event) => setDraftPillars((items) => items.map((entry, i) => i === index ? { ...entry, name: event.target.value } : entry))} style={{ width: '100%', marginTop: 4 }} />
            </label>
            <label style={{ display: 'block', fontSize: 13, marginTop: 8 }}>方向说明
              <textarea className="input" value={pillar.description} maxLength={600} rows={2} onChange={(event) => setDraftPillars((items) => items.map((entry, i) => i === index ? { ...entry, description: event.target.value } : entry))} style={{ width: '100%', marginTop: 4 }} />
            </label>
            <label style={{ display: 'block', fontSize: 13, marginTop: 8 }}>未来四周测试资源分配（%）
              <input className="input" type="number" min={0} max={100} step={1} value={pillar.allocation_ratio} onChange={(event) => setDraftPillars((items) => items.map((entry, i) => i === index ? { ...entry, allocation_ratio: Number(event.target.value) } : entry))} style={{ width: 120, marginTop: 4 }} />
            </label>
          </article>)}
        </div>
        <div style={{ marginTop: 10, fontWeight: 600, color: ratioTotal === 100 ? 'var(--green)' : 'var(--red)' }}>
          当前合计：{ratioTotal}% {ratioTotal === 100 ? '✓' : '· 合计为 100% 才能确认'}
        </div>
        <p className="page-subtitle">比例代表未来四周的测试资源分配，不是固定发布配比。历史表现、样本和基准仅供查看，不可在此修改。</p>
        <h4 style={{ margin: '14px 0 6px' }}>未来四周重点验证</h4>
        {experimentQuestions.map((test) => <div className="page-subtitle" key={test.pillar_name} style={{ marginTop: 4 }}>· {test.question}</div>)}
        {!summaryOpen ? <button className="btn btn-sm btn-primary" style={{ marginTop: 12 }} disabled={ratioTotal !== 100 || !draftPositioning.trim()} onClick={() => setSummaryOpen(true)}>查看确认摘要</button> : <div className="card" style={{ padding: 12, marginTop: 12 }}>
          <h4 style={{ margin: '0 0 6px' }}>确认摘要</h4>
          <div>账号：{account.name}</div><div>策略版本：V1</div><div>测试周期：4 周</div>
          <div>有效历史作品：{recommendation.source.canonical_sample_size} 条</div>
          <div>策略可信度：{recommendation.confidence === 'LOW' ? '较低' : recommendation.confidence}</div>
          <div>内容方向：{draftPillars.map((pillar) => `${pillar.name} ${pillar.allocation_ratio}%`).join(' · ')}</div>
          <p className="page-subtitle">确认后账号将进入正式运营状态，后续选题会依据该策略生成。LOW 表示第一阶段实验方案，未来根据真实运营数据持续调整。</p>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-sm" disabled={busy} onClick={() => setSummaryOpen(false)}>返回调整</button>
            <button className="btn btn-sm btn-primary" disabled={busy || ratioTotal !== 100} onClick={() => void confirm()}>{busy ? '正在启用…' : '确认并启用'}</button>
          </div>
        </div>}
      </div>}
    </div>}
    {(!active || item?.status !== 'CURRENT') && <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 14 }}>
      <button className="btn btn-sm btn-primary" disabled={busy} onClick={() => void generate()}>
        {busy ? '正在整理建议…' : item ? '重新生成建议' : '生成策略建议'}
      </button>
      {!active && <span className="page-subtitle" style={{ alignSelf: 'center' }}>策略建议不会自动确认或启用。</span>}
    </div>}
    {history.length > 1 && <details style={{ marginTop: 12 }}><summary style={{ cursor: 'pointer' }}>历史版本（{history.length}）</summary>
      {history.map((v) => <div key={v.id} className="page-subtitle" style={{ marginTop: 6 }}>V{v.version} · {v.status} · {v.generated_at}</div>)}
    </details>}
  </section>;
}
