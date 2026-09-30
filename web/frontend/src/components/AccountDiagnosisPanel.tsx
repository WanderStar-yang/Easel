import { useCallback, useEffect, useState } from 'react';
import {
  fetchDiagnosisHistory, fetchHistoricalPosts, fetchLatestDiagnosis,
  getHistoricalCompleteness, runAccountDiagnosis,
} from '../lib/api';
import type { AccountDiagnosisReport, HistoricalCompleteness, OperatorAccount } from '../lib/api';

function formatMetric(value: unknown): string {
  return typeof value === 'number' ? new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 3 }).format(value) : '—';
}

function metricMedian(summary: Record<string, unknown>, key: string): string {
  const entry = summary[key];
  if (!entry || typeof entry !== 'object') return '—';
  return formatMetric((entry as { median?: unknown }).median);
}

function postField(post: Record<string, unknown>, key: string): string {
  const value = post[key];
  if (Array.isArray(value) && value.length) return value.join('、');
  if (value != null && value !== '' && !Array.isArray(value)) return String(value);
  return ({ content_type: '未分类', hook_type: '未标注 / 无数据', subjects: '未标注主体', duration: '暂无数据' } as Record<string, string>)[key] || '—';
}

function ConfidenceBadge({ confidence }: { confidence: string }) {
  const label = confidence === 'HIGH' ? '高' : confidence === 'MEDIUM' ? '中' : '低';
  return <span className={`badge ${confidence === 'HIGH' ? 'badge-ok' : ''}`}>{label}置信度</span>;
}

export default function AccountDiagnosisPanel({ account, onClose, onOpenHistory, onOpenCreatorSync }: {
  account: OperatorAccount; onClose: () => void; onOpenHistory: () => void; onOpenCreatorSync: () => void;
}) {
  const [postCount, setPostCount] = useState(0);
  const [completeness, setCompleteness] = useState<HistoricalCompleteness | null>(null);
  const [diagnosis, setDiagnosis] = useState<AccountDiagnosisReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [historyCount, setHistoryCount] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [posts, quality, latest, history] = await Promise.all([
        fetchHistoricalPosts(account.id), getHistoricalCompleteness(account.id),
        fetchLatestDiagnosis(account.id).catch(() => null),
        fetchDiagnosisHistory(account.id).catch(() => []),
      ]);
      setPostCount(posts.total);
      setCompleteness(quality);
      setDiagnosis(latest);
      setHistoryCount(history.length);
    } catch {
      setError('加载账号历史或完整度失败，请重试。');
    } finally {
      setLoading(false);
    }
  }, [account.id]);

  useEffect(() => { void load(); }, [load]);

  const run = async () => {
    setRunning(true);
    setError('');
    try {
      setDiagnosis(await runAccountDiagnosis(account.id));
      const quality = await getHistoricalCompleteness(account.id);
      setCompleteness(quality);
      setHistoryCount((count) => count + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : '诊断失败，请检查历史数据。');
    } finally {
      setRunning(false);
    }
  };

  const metricSummary = diagnosis?.metric_summary || {};
  const distribution = diagnosis?.content_distribution || {};

  return (
    <section className="card" style={{ marginTop: 20, padding: 18 }} aria-label={`${account.name}首次诊断`}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 19 }}>{account.name} · 首次账号诊断</h2>
          <p className="page-subtitle" style={{ margin: '5px 0 0' }}>
            当前账号：{account.platform === 'douyin' ? '抖音宠物账号' : '小红书独立开发者账号'}。结论只基于此账号历史内容。
          </p>
        </div>
        <button className="btn btn-sm" onClick={onClose}>收起</button>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 14 }}>
        <span className="badge">历史作品 {postCount} 条</span>
        <span className="badge">数据完整度 {completeness?.score ?? 0}%</span>
        <span className="badge">当前状态 {diagnosis?.account.status || account.status}</span>
        {diagnosis && <ConfidenceBadge confidence={diagnosis.confidence} />}
        {postCount > 0 && <button className="btn btn-sm btn-primary" disabled={loading || running}
          onClick={() => void run()}>
          {running ? '正在分析…' : diagnosis ? '重新诊断' : '开始首次诊断'}
        </button>}
      </div>
      {postCount === 0 && !loading && (
        <div role="status" className="card" style={{ marginTop: 14, padding: 16 }}>
          <h3 style={{ margin: '0 0 7px', fontSize: 16 }}>首次账号诊断需要历史作品数据</h3>
          <p style={{ margin: '0 0 12px', color: 'var(--text-secondary)', fontSize: 13 }}>
            当前账号还没有历史作品数据。{account.platform === 'douyin'
              ? '建议先从抖音创作者中心同步历史作品。'
              : '请先导入或手动添加历史作品。'}
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {account.platform === 'douyin' && <button className="btn btn-sm btn-primary" onClick={onOpenCreatorSync}>同步抖音数据</button>}
            <button className="btn btn-sm" onClick={onOpenHistory}>导入 CSV/XLSX</button>
            <button className="btn btn-sm" onClick={onOpenHistory}>手动添加</button>
          </div>
        </div>
      )}
      {error && <div role="alert" style={{ color: 'var(--red)', fontSize: 13, marginTop: 12 }}>{error}</div>}

      {diagnosis && (
        <div style={{ display: 'grid', gap: 14, marginTop: 16 }}>
          {diagnosis.status === 'STALE' && (
            <div role="alert" className="card" style={{ padding: 12, color: 'var(--red)' }}>
              历史数据已更新，请重新运行账号诊断。当前展示的是更新前报告。
            </div>
          )}
          <section className="card" style={{ padding: 14 }}>
            <h3 style={{ margin: '0 0 7px', fontSize: 15 }}>诊断概览</h3>
            <div style={{ fontSize: 13, lineHeight: 1.7 }}>{diagnosis.overview}</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>
              置信度规则：{diagnosis.data_quality.confidence_rules.HIGH}；{diagnosis.data_quality.confidence_rules.MEDIUM}；其余为 LOW。
              报告历史记录 {historyCount} 份。
            </div>
            {diagnosis.account_context.strategy_is_initial_hypothesis && (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>
                现有 Strategy 仅作初始假设上下文，没有作为诊断结论依据。
              </div>
            )}
            {diagnosis.ai_explanation.status === 'available' && diagnosis.ai_explanation.summary ? (
              <div style={{ marginTop: 10, fontSize: 13, lineHeight: 1.7 }}>{diagnosis.ai_explanation.summary}</div>
            ) : (
              <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
                AI 解释不可用；本地统计和规则化结论仍可查看。
              </div>
            )}
          </section>

          <section className="card" style={{ padding: 14 }}>
            <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>关键指标（中位数）</h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {(account.platform === 'douyin'
                ? [['views', '播放'], ['likes', '点赞'], ['comments', '评论'], ['favorites', '收藏'], ['shares', '分享'], ['followers_gain', '涨粉'], ['engagement_rate', '互动率']]
                : [['views', '曝光/浏览'], ['likes', '点赞'], ['favorites', '收藏'], ['comments', '评论'], ['shares', '分享'], ['followers_gain', '涨粉'], ['profile_visits', '主页访问'], ['inquiries', '咨询'], ['engagement_rate', '互动率']]
              ).map(([key, label]) => (
                <span key={key} className="badge">{label}：{key === 'engagement_rate'
                  ? `${formatMetric(metricMedian(metricSummary, key) === '—' ? null : Number(metricMedian(metricSummary, key)) * 100)}%`
                  : metricMedian(metricSummary, key)}</span>
              ))}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 9 }}>
              互动率公式：{diagnosis.engagement_rate_formula}。仅对播放/曝光大于 0 且至少有一个互动指标的作品计算。
            </div>
          </section>

          <section className="card" style={{ padding: 14 }}>
            <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>内容结构</h3>
            <div style={{ display: 'grid', gap: 8 }}>
              {Object.entries(distribution).map(([dimension, groups]) => (
                <div key={dimension} style={{ fontSize: 12 }}>
                  <strong>{dimension}</strong>：{Object.entries(groups).map(([label, count]) => `${label} ${count}`).join(' · ') || '暂无'}
                </div>
              ))}
            </div>
          </section>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
            {[['高表现内容', diagnosis.top_posts], ['低表现内容', diagnosis.low_posts]].map(([title, items]) => (
              <section key={String(title)} className="card" style={{ padding: 14 }}>
                <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>{String(title)}（{diagnosis.ranking_rule}）</h3>
                {(items as Array<Record<string, unknown>>).length ? (items as Array<Record<string, unknown>>).map((post) => (
                  <div key={String(post.id)} style={{ borderTop: '1px solid var(--border)', padding: '7px 0', fontSize: 12 }}>
                    <strong>{String(post.title || '无标题')}</strong><br />
                    播放/曝光 {postField(post, 'views')} · 点赞 {postField(post, 'likes')} · 类型 {postField(post, 'content_type')}
                  </div>
                )) : <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>没有可按播放/曝光排序的作品。</div>}
              </section>
            ))}
          </div>

          <section className="card" style={{ padding: 14 }}>
            <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>可观察模式</h3>
            {diagnosis.pattern_findings.length ? diagnosis.pattern_findings.map((finding, index) => (
              <div key={`${finding.dimension}-${finding.metric}-${index}`} style={{ borderTop: '1px solid var(--border)', padding: '8px 0', fontSize: 12 }}>
                <ConfidenceBadge confidence={finding.confidence} />{' '}
                {finding.dimension}：{finding.pattern}；{finding.metric} {formatMetric(finding.value_a)} vs {formatMetric(finding.value_b)}；
                样本 {finding.sample_a}/{finding.sample_b}，差异 {finding.difference_percent}%
              </div>
            )) : <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>目前没有满足最小样本条件的分组差异。</div>}
          </section>

          {(['strengths', 'problems', 'opportunities'] as const).map((key) => (
            <section key={key} className="card" style={{ padding: 14 }}>
              <h3 style={{ margin: '0 0 7px', fontSize: 15 }}>{{ strengths: '优势', problems: '问题', opportunities: '可验证机会' }[key]}</h3>
              <ul style={{ margin: 0, paddingLeft: 20, fontSize: 12, lineHeight: 1.7 }}>
                {diagnosis[key].map((item, index) => <li key={`${key}-${index}`}>{item}</li>)}
              </ul>
            </section>
          ))}

          {diagnosis.insufficient_data.length > 0 && (
            <section className="card" style={{ padding: 14 }}>
              <h3 style={{ margin: '0 0 7px', fontSize: 15 }}>数据不足项</h3>
              <ul style={{ margin: 0, paddingLeft: 20, fontSize: 12, lineHeight: 1.7 }}>
                {diagnosis.insufficient_data.map((item, index) => <li key={`insufficient-${index}`}>{item}</li>)}
              </ul>
            </section>
          )}
          {diagnosis.save_value_signal && <div className="page-subtitle">收藏信号：
            {diagnosis.save_value_signal.favorites_to_views_median != null
              ? `收藏/曝光中位数 ${(diagnosis.save_value_signal.favorites_to_views_median * 100).toFixed(2)}%（${diagnosis.save_value_signal.sample_size} 条） · ` : ''}
            {diagnosis.save_value_signal.note}
          </div>}
          {diagnosis.ip_business_signals && <div className="page-subtitle">主页访问中位数 {formatMetric(diagnosis.ip_business_signals.profile_visits_median)}；咨询中位数 {formatMetric(diagnosis.ip_business_signals.inquiries_median)}。{diagnosis.ip_business_signals.interpretation}</div>}
          <div className="page-subtitle">当前状态保持在 {diagnosis.account.status}。本阶段不建立 Baseline、不生成正式 Strategy，也不激活账号。</div>
        </div>
      )}
    </section>
  );
}
