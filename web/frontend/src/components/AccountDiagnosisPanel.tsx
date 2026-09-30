import { useCallback, useEffect, useState } from 'react';
import {
  fetchDiagnosisHistory, fetchHistoricalPosts, fetchLatestDiagnosis,
  getHistoricalCompleteness, runAccountDiagnosis, fetchLatestBaseline,
} from '../lib/api';
import type { AccountBaseline, AccountDiagnosisReport, HistoricalCompleteness, OperatorAccount } from '../lib/api';

function formatMetric(value: unknown): string {
  return typeof value === 'number' ? new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(value) : '暂无数据';
}

function metricMedian(summary: Record<string, unknown>, key: string): unknown {
  const entry = summary[key];
  return entry && typeof entry === 'object' ? (entry as { median?: unknown }).median : null;
}

function confidenceLabel(value: string): string {
  return value === 'HIGH' ? '高' : value === 'MEDIUM' ? '中等' : '低';
}

function postTime(value: unknown): string {
  return typeof value === 'string' && value ? new Date(value).toLocaleDateString('zh-CN') : '';
}

export default function AccountDiagnosisPanel({ account, onClose, onOpenHistory, onImportDouyinExport, onOpenBaseline }: {
  account: OperatorAccount; onClose: () => void; onOpenHistory: () => void; onImportDouyinExport: () => void; onOpenBaseline: () => void;
}) {
  const [postCount, setPostCount] = useState(0);
  const [rawCount, setRawCount] = useState(0);
  const [completeness, setCompleteness] = useState<HistoricalCompleteness | null>(null);
  const [diagnosis, setDiagnosis] = useState<AccountDiagnosisReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [historyCount, setHistoryCount] = useState(0);
  const [baseline, setBaseline] = useState<AccountBaseline | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [posts, quality, latest, history, latestBaseline] = await Promise.all([
        fetchHistoricalPosts(account.id), getHistoricalCompleteness(account.id),
        fetchLatestDiagnosis(account.id).catch(() => null),
        fetchDiagnosisHistory(account.id).catch(() => []),
        fetchLatestBaseline(account.id).catch(() => null),
      ]);
      setPostCount(posts.total);
      setRawCount(posts.raw_total ?? posts.total);
      setCompleteness(quality);
      setDiagnosis(latest);
      setHistoryCount(history.length);
      setBaseline(latestBaseline);
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
      const [quality, posts, history] = await Promise.all([
        getHistoricalCompleteness(account.id), fetchHistoricalPosts(account.id), fetchDiagnosisHistory(account.id),
      ]);
      setCompleteness(quality);
      setPostCount(posts.total);
      setRawCount(posts.raw_total ?? posts.total);
      setHistoryCount(history.length);
    } catch (err) {
      setError(err instanceof Error ? err.message : '诊断失败，请检查历史数据。');
    } finally {
      setRunning(false);
    }
  };

  const stale = diagnosis?.status === 'STALE';
  const metrics = diagnosis?.metric_summary || {};
  const recordCounts = diagnosis?.record_counts;
  const confidence = diagnosis?.confidence || 'LOW';
  const metricCards = account.platform === 'douyin'
    ? [['views', '播放中位数'], ['likes', '点赞中位数'], ['comments', '评论中位数'], ['favorites', '收藏中位数'], ['shares', '分享中位数'], ['engagement_rate', '互动率']]
    : [['views', '曝光中位数'], ['likes', '点赞中位数'], ['comments', '评论中位数'], ['favorites', '收藏中位数'], ['shares', '分享中位数'], ['engagement_rate', '互动率']];

  return (
    <section className="card" style={{ marginTop: 20, padding: 18 }} aria-label={`${account.name}账号诊断`}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 19 }}>{account.name} · 账号诊断</h2>
          <p className="page-subtitle" style={{ margin: '5px 0 0' }}>
            当前账号：{account.platform === 'douyin' ? '抖音宠物账号' : '小红书独立开发者账号'}。诊断只使用本账号的有效唯一作品。
          </p>
        </div>
        <button className="btn btn-sm" onClick={onClose}>收起</button>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 14 }}>
        <span className="badge">有效作品 {postCount} 条</span>
        <span className="badge">数据完整度 {completeness?.score ?? 0}%</span>
        {diagnosis && <span className={`badge ${confidence === 'HIGH' ? 'badge-ok' : ''}`}>诊断可信度：{confidenceLabel(confidence)}</span>}
        {postCount > 0 && <button className="btn btn-sm btn-primary" disabled={loading || running} onClick={() => void run()}>
          {running ? '正在诊断…' : diagnosis ? '重新诊断' : '开始诊断'}
        </button>}
      </div>

      {diagnosis && !stale && postCount > 0 && (
        <section className="card" style={{ marginTop: 14, padding: 13, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <strong>{baseline?.status === 'ACTIVE' ? '历史基准已建立' : baseline?.status === 'STALE' ? '历史基准需要更新' : '诊断已完成，可以建立历史基准'}</strong>
            <div className="page-subtitle" style={{ marginTop: 4 }}>
              {baseline?.status === 'STALE' ? '历史数据已发生变化，请重新生成基准。' : '基准只记录历史作品的典型表现，不提供运营建议。'}
            </div>
          </div>
          <button className="btn btn-sm btn-primary" onClick={onOpenBaseline}>
            {baseline?.status === 'ACTIVE' ? '查看历史基准' : baseline?.status === 'STALE' ? '重新生成历史基准' : '建立历史基准'}
          </button>
        </section>
      )}

      {postCount === 0 && !loading && (
        <div role="status" className="card" style={{ marginTop: 14, padding: 16 }}>
          <h3 style={{ margin: '0 0 7px', fontSize: 16 }}>诊断需要历史作品数据</h3>
          <p className="page-subtitle">{account.platform === 'douyin' ? '请先导入 PC 端抖音创作者中心导出的作品列表。' : '请先导入或手动添加历史作品。'}</p>
          <div style={{ display: 'flex', gap: 8 }}>
            {account.platform === 'douyin' && <button className="btn btn-sm btn-primary" onClick={onImportDouyinExport}>导入抖音作品数据</button>}
            <button className="btn btn-sm" onClick={onOpenHistory}>查看历史内容</button>
          </div>
        </div>
      )}
      {error && <div role="alert" style={{ color: 'var(--red)', fontSize: 13, marginTop: 12 }}>{error}</div>}

      {diagnosis && (stale ? (
        <div style={{ marginTop: 16 }}>
          <div role="alert" className="card" style={{ padding: 14, color: 'var(--red)' }}>
            历史数据已更新，当前诊断已过期。旧报告已收起，请重新诊断后查看最新结果。
            <div style={{ marginTop: 10 }}><button className="btn btn-sm btn-primary" disabled={running} onClick={() => void run()}>
              {running ? '正在重新诊断…' : '重新诊断'}
            </button></div>
          </div>
          <details style={{ marginTop: 10 }}>
            <summary>查看已过期报告</summary>
            <div className="card" style={{ marginTop: 8, padding: 12 }}>{diagnosis.overview}</div>
          </details>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 14, marginTop: 16 }}>
          <section className="card" style={{ padding: 14 }}>
            <h3 style={{ margin: '0 0 7px', fontSize: 15 }}>一句话诊断</h3>
            <div style={{ fontSize: 14, lineHeight: 1.8 }}>{diagnosis.overview}</div>
            <div className="page-subtitle" style={{ marginTop: 7 }}>
              诊断可信度：{confidenceLabel(confidence)}。{diagnosis.confidence_copy}
            </div>
          </section>

          <section className="card" style={{ padding: 14 }}>
            <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>账号基准表现</h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {metricCards.map(([key, label]) => <span key={key} className="badge">{label}：{key === 'engagement_rate'
                ? (typeof metricMedian(metrics, key) === 'number' ? `${formatMetric(Number(metricMedian(metrics, key)) * 100)}%` : '暂无数据')
                : formatMetric(metricMedian(metrics, key))}</span>)}
            </div>
            <p className="page-subtitle" style={{ margin: '9px 0 0' }}>中位数代表典型作品表现，不容易被单条高流量作品影响。</p>
            <details style={{ marginTop: 8 }}><summary>查看计算方式</summary>
              <p className="page-subtitle">互动率按有数据的点赞、评论、收藏和分享总和除以播放/曝光计算；缺失项不按 0 处理，播放/曝光为 0 的作品不计算。</p>
            </details>
          </section>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
            {([['表现最好的内容', diagnosis.top_posts], ['表现较弱的内容', diagnosis.low_posts]] as const).map(([title, items]) => (
              <section key={title} className="card" style={{ padding: 14 }}>
                <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>{title}</h3>
                {items.length ? items.map((post) => <div key={String(post.id)} style={{ borderTop: '1px solid var(--border)', padding: '8px 0', fontSize: 12 }}>
                  <strong>{String(post.title || '无标题')}</strong><br />
                  播放/曝光 {formatMetric(post.views)} · 点赞 {formatMetric(post.likes)} · 评论 {formatMetric(post.comments)}
                  {postTime(post.publish_time) && <> · {postTime(post.publish_time)}</>}
                  {typeof post.content_type === 'string' && post.content_type && <> · {post.content_type}</>}
                </div>) : <div className="page-subtitle">当前没有可比较的作品。</div>}
              </section>
            ))}
          </div>

          <section className="card" style={{ padding: 14 }}>
            <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>当前发现</h3>
            {([['优势', diagnosis.strengths], ['问题', diagnosis.problems], ['机会', diagnosis.opportunities]] as const).map(([label, items]) => (
              <div key={label} style={{ marginTop: 8 }}><strong>{label}</strong>
                <ul style={{ margin: '4px 0 0', paddingLeft: 20, fontSize: 13, lineHeight: 1.7 }}>{items.map((item, index) => <li key={`${label}-${index}`}>{item}</li>)}</ul>
              </div>
            ))}
          </section>

          <section className="card" style={{ padding: 14 }}>
            <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>当前数据不足</h3>
            {diagnosis.data_gaps.length ? <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13, lineHeight: 1.7 }}>
              {diagnosis.data_gaps.map((gap) => <li key={gap.field}>{gap.label}缺少 {gap.missing_count} 条：{gap.impact}</li>)}
            </ul> : <div className="page-subtitle">当前核心诊断字段没有明显缺口。</div>}
          </section>

          <section className="card" style={{ padding: 14 }}>
            <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>下一步建议</h3>
            <p className="page-subtitle" style={{ marginTop: 0 }}>补充内容类型、主体和真实拍摄/AI 分类后重新诊断，才能比较不同内容方向。</p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              <button className="btn btn-sm btn-primary" onClick={onOpenHistory}>快速分类历史作品</button>
              {account.platform === 'douyin' && <button className="btn btn-sm" onClick={onImportDouyinExport}>补充作品数据</button>}
              <button className="btn btn-sm" disabled={running} onClick={() => void run()}>{running ? '正在重新诊断…' : '重新诊断'}</button>
            </div>
          </section>

          <details className="card" style={{ padding: 12 }}>
            <summary>查看诊断技术详情 / 开发信息</summary>
            <div style={{ display: 'grid', gap: 8, marginTop: 10, fontSize: 12 }}>
              <div>数据库原始记录 {recordCounts?.raw_record_count ?? rawCount} 条 · 有效唯一作品 {recordCounts?.unique_post_count ?? postCount} 条 · 当前诊断样本 {recordCounts?.diagnosis_sample_count ?? diagnosis.input_evidence.sample_size} 条</div>
              {(recordCounts?.excluded_stale_count || 0) > 0 && <div>最新完整快照之外的旧记录：{recordCounts?.excluded_stale_count} 条</div>}
              {(recordCounts?.archived_legacy_count || 0) > 0 && <div>已通过官方作品身份归档的旧扫描记录：{recordCounts?.archived_legacy_count} 条</div>}
              {(recordCounts?.suspected_duplicate_count || 0) > 0 && <div>检测到 {recordCounts?.suspected_duplicate_count} 条疑似重复记录；已按官方快照身份修复并归档可确认记录。</div>}
              <div>算法版本 {diagnosis.algorithm_version} · 报告历史 {historyCount} 份 · 完整度 {completeness?.score ?? 0}%</div>
              <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify({ metric_coverage: diagnosis.data_quality.metric_coverage, content_distribution: diagnosis.content_distribution, confidence_rules: diagnosis.data_quality.confidence_rules, pattern_findings: diagnosis.pattern_findings, ai_explanation: diagnosis.ai_explanation }, null, 2)}</pre>
            </div>
          </details>
        </div>
      ))}
    </section>
  );
}
