import { useCallback, useEffect, useState } from 'react';
import {
  fetchBaselineHistory, fetchLatestBaseline, generateAccountBaseline, previewAccountBaseline,
} from '../lib/api';
import type { AccountBaseline, AccountBaselinePreview, OperatorAccount } from '../lib/api';

const METRIC_LABELS: Record<string, string> = {
  views: '播放', likes: '点赞', comments: '评论', favorites: '收藏', shares: '分享',
  engagement_rate: '互动率', followers_gain: '涨粉', profile_visits: '主页访问', inquiries: '咨询',
};
const SEGMENT_LABELS: Record<string, string> = {
  content_source: '内容来源', content_type: '内容类型', subjects: '出镜主体', hook_type: '开场方式',
  duration_bucket: '视频时长', publish_period: '发布时间段',
};
const fmt = (value: number | null | undefined, metric = '') => {
  if (typeof value !== 'number') return '暂无数据';
  const rendered = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(
    metric === 'engagement_rate' ? value * 100 : value,
  );
  return metric === 'engagement_rate' ? `${rendered}%` : rendered;
};
const pct = (value: number | undefined) => `${Math.round((value || 0) * 100)}%`;
const dateRange = (start: string | null, end: string | null) => `${start || '日期未提供'} ～ ${end || '日期未提供'}`;

function Metrics({ metrics, showRange = false }: { metrics: Record<string, { median: number | null; p25: number | null; p75: number | null; sample_count: number; coverage: number }>; showRange?: boolean }) {
  return <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(155px, 1fr))', gap: 8 }}>
    {Object.entries(METRIC_LABELS).map(([key, label]) => {
      const item = metrics[key];
      return <div className="card" key={key} style={{ padding: 11 }}>
        <div className="page-subtitle">{label}中位数</div>
        <strong style={{ display: 'block', fontSize: 20, marginTop: 3 }}>{fmt(item?.median, key)}</strong>
        <div className="page-subtitle" style={{ marginTop: 4 }}>样本 {item?.sample_count ?? 0} 条 · 覆盖 {pct(item?.coverage)}</div>
        {showRange && <div className="page-subtitle" style={{ marginTop: 2 }}>P25 {fmt(item?.p25, key)} · P75 {fmt(item?.p75, key)}</div>}
      </div>;
    })}
  </div>;
}

export default function AccountBaselinePanel({ account, onClose, onOpenHistory }: {
  account: OperatorAccount; onClose: () => void; onOpenHistory: () => void;
}) {
  const [baseline, setBaseline] = useState<AccountBaseline | null>(null);
  const [history, setHistory] = useState<AccountBaseline[]>([]);
  const [preview, setPreview] = useState<AccountBaselinePreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const [latest, versions] = await Promise.all([fetchLatestBaseline(account.id), fetchBaselineHistory(account.id)]);
      setBaseline(latest);
      setHistory(versions);
    } catch {
      setError('加载历史基准失败，请重试。');
    }
  }, [account.id]);
  useEffect(() => { void load(); }, [load]);

  const makePreview = async () => {
    setBusy(true); setError('');
    try { setPreview(await previewAccountBaseline(account.id)); }
    catch (err) { setError(err instanceof Error ? err.message : '无法生成基准预览。'); }
    finally { setBusy(false); }
  };

  const confirm = async () => {
    if (!preview) return;
    setBusy(true); setError('');
    try {
      await generateAccountBaseline(account.id, preview.historical_data_version);
      setPreview(null);
      await load();
    } catch (err) { setError(err instanceof Error ? err.message : '建立历史基准失败。'); }
    finally { setBusy(false); }
  };

  const shown = preview || baseline;
  const metrics = shown?.metrics || {};
  const segments = shown?.segments || {};
  return <section className="card" style={{ marginTop: 16, padding: 18 }} aria-label={`${account.name}历史基准`}>
    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
      <div>
        <h2 style={{ margin: 0, fontSize: 19 }}>账号历史基准</h2>
        <p className="page-subtitle" style={{ margin: '5px 0 0' }}>这里展示历史作品中位数，代表账号在开始新的运营策略前的典型表现。</p>
      </div>
      <button className="btn btn-sm" onClick={onClose}>收起</button>
    </div>
    {error && <div role="alert" style={{ color: 'var(--red)', marginTop: 12 }}>{error}</div>}

    {!preview && baseline && <div style={{ marginTop: 14 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
        <span className={`badge ${baseline.status === 'ACTIVE' ? 'badge-ok' : ''}`}>{baseline.status === 'ACTIVE' ? `当前有效基准 V${baseline.version}` : `基准 V${baseline.version} 已过期`}</span>
        <span className="badge">基于 {baseline.sample_size} 条有效历史作品</span>
        <span className="badge">数据周期：{dateRange(baseline.period_start, baseline.period_end)}</span>
      </div>
      {baseline.status === 'STALE' && <p role="status" style={{ color: 'var(--red)' }}>历史数据已发生变化，请重新生成基准。</p>}
      <Metrics metrics={metrics} showRange />
      <p className="page-subtitle" style={{ marginTop: 10 }}>中位数不容易被单条高播放作品拉高。覆盖率和样本数说明每项指标实际依据多少条作品。</p>
    </div>}

    {preview && <div className="card" style={{ marginTop: 14, padding: 14 }}>
      <h3 style={{ margin: '0 0 8px', fontSize: 16 }}>建立前预览</h3>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
        <span className="badge">有效作品：{preview.sample_size} 条</span>
        <span className="badge">时间范围：{dateRange(preview.period_start, preview.period_end)}</span>
        <span className="badge">播放覆盖：{pct(preview.metrics.views?.coverage)}</span>
        <span className="badge">互动率覆盖：{pct(preview.metrics.engagement_rate?.coverage)}</span>
        <span className="badge">内容分类覆盖：{pct(preview.content_type_coverage)}</span>
      </div>
      <Metrics metrics={preview.metrics} showRange />
      <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
        <button className="btn btn-sm btn-primary" disabled={busy} onClick={() => void confirm()}>{busy ? '正在建立…' : '确认建立基准'}</button>
        <button className="btn btn-sm" disabled={busy} onClick={() => setPreview(null)}>取消</button>
      </div>
    </div>}

    {shown && <section style={{ marginTop: 18 }}>
      <h3 style={{ margin: '0 0 9px', fontSize: 16 }}>内容分类基准</h3>
      {Object.entries(SEGMENT_LABELS).map(([key, label]) => {
        const segment = segments[key];
        if (!segment?.groups?.length) return null;
        return <div key={key} className="card" style={{ padding: 12, marginTop: 8 }}>
          <h4 style={{ margin: '0 0 8px', fontSize: 14 }}>{label} · 分类覆盖 {pct(segment.coverage)}</h4>
          {segment.groups.map((group) => <div key={group.key} style={{ padding: '8px 0', borderTop: '1px solid var(--border)' }}>
            <strong>{group.key}</strong> <span className="page-subtitle">样本：{group.sample_size} 条{group.eligible_for_comparison ? ' · 可供后续正式比较' : ' · 初步基准'}</span>
            <div className="page-subtitle" style={{ marginTop: 3 }}>播放中位数：{fmt(group.metrics.views?.median)} · 点赞：{fmt(group.metrics.likes?.median)} · 互动率：{fmt(group.metrics.engagement_rate?.median, 'engagement_rate')}</div>
          </div>)}
        </div>;
      })}
      {!['content_source', 'content_type', 'subjects', 'hook_type'].some((key) => segments[key]?.groups?.length > 0) && <div className="card" style={{ padding: 13 }}>
        <p className="page-subtitle" style={{ margin: 0 }}>尚未完成足够作品分类，暂时无法建立内容分组基准。</p>
        <button className="btn btn-sm" style={{ marginTop: 9 }} onClick={onOpenHistory}>去分类历史作品</button>
      </div>}
    </section>}

    {!preview && <div style={{ marginTop: 15 }}>
      <button className="btn btn-sm btn-primary" disabled={busy} onClick={() => void makePreview()}>
        {busy ? '正在计算预览…' : baseline?.status === 'STALE' ? '重新生成历史基准' : baseline ? '重新生成新版本' : '建立历史基准'}
      </button>
    </div>}
    {shown && <details style={{ marginTop: 12 }}><summary>数据版本与历史记录</summary>
      <p className="page-subtitle">生成于 {new Date(shown.generated_at).toLocaleString('zh-CN')}。当前版本以 canonical 唯一作品计算；归档重复记录不参与。</p>
      {history.length > 1 && <ul className="page-subtitle">{history.map((item) => <li key={item.id}>V{item.version} · {item.status === 'ACTIVE' ? '当前有效' : '历史版本/已过期'} · {item.sample_size} 条作品 · {new Date(item.generated_at).toLocaleDateString('zh-CN')}</li>)}</ul>}
      {(preview?.metric_todo || baseline?.metrics.completion_rate?.sample_count === 0) && <p className="page-subtitle">完播率、2秒跳出率和平均播放时长尚未由当前官方导入字段可靠解析，暂不进入基准。</p>}
    </details>}
  </section>;
}
