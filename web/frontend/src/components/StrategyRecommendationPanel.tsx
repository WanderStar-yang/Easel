import { useCallback, useEffect, useState } from 'react';
import { fetchStrategyRecommendation, fetchStrategyRecommendationHistory, generateStrategyRecommendation } from '../lib/api';
import type { StrategyRecommendation, OperatorAccount } from '../lib/api';

const LEVEL: Record<string, string> = { SUPPORTED: '有历史样本支持', EXPERIMENTAL: '初步数据，需验证', INSUFFICIENT_DATA: '数据不足' };
const dim: Record<string, string> = { subjects: '出镜主体', content_type: '内容类型', content_source: '内容来源' };

export default function StrategyRecommendationPanel({ account, onClose }: { account: OperatorAccount; onClose: () => void }) {
  const [item, setItem] = useState<StrategyRecommendation | null>(null);
  const [history, setHistory] = useState<StrategyRecommendation[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const [latest, versions] = await Promise.all([
        fetchStrategyRecommendation(account.id), fetchStrategyRecommendationHistory(account.id),
      ]);
      setItem(latest); setHistory(versions);
    } catch { setError('加载策略建议失败，请重试。'); }
  }, [account.id]);
  useEffect(() => { void load(); }, [load]);

  const generate = async () => {
    setBusy(true); setError('');
    try { await generateStrategyRecommendation(account.id); await load(); }
    catch (err) { setError(err instanceof Error ? err.message : '生成策略建议失败。'); }
    finally { setBusy(false); }
  };

  const recommendation = item?.recommendation;
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
        <span className="badge">整体置信度：{recommendation.confidence}</span>
        {recommendation.source.baseline_version && <span className="badge">历史基准 V{recommendation.source.baseline_version}</span>}
        <span className="badge">有效历史作品 {recommendation.source.canonical_sample_size} 条</span>
      </div>
      <p className="page-subtitle">{recommendation.confidence_note}</p>
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
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 14 }}>
      <button className="btn btn-sm btn-primary" disabled={busy} onClick={() => void generate()}>
        {busy ? '正在整理建议…' : item ? '重新生成建议' : '生成策略建议'}
      </button>
      <span className="page-subtitle" style={{ alignSelf: 'center' }}>仅保存建议，不会确认或启用策略。</span>
    </div>
    {history.length > 1 && <details style={{ marginTop: 12 }}><summary style={{ cursor: 'pointer' }}>历史版本（{history.length}）</summary>
      {history.map((v) => <div key={v.id} className="page-subtitle" style={{ marginTop: 6 }}>V{v.version} · {v.status} · {v.generated_at}</div>)}
    </details>}
  </section>;
}
