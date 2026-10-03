import { useId, useState } from 'react';
import type { Point, Trend } from './types';

export function LineChart({ points, color = 'var(--lime)', compact = false, label = 'Observed series', unit = '' }: { points: Point[]; color?: string; compact?: boolean; label?: string; unit?: string }) {
  const id = useId().replaceAll(':', '');
  const [hover, setHover] = useState<number | null>(null);
  if (points.length < 2) return <div className="empty-chart">{points.length === 1 ? 'One recorded point. History will grow with scheduled updates.' : 'Waiting for observations.'}</div>;
  const width = compact ? 150 : 800, height = compact ? 44 : 245, padX = compact ? 1 : 52, padY = compact ? 3 : 22;
  const values = points.map(p => p.value), min = Math.min(...values), max = Math.max(...values), span = Math.max(max - min, 0.01);
  const coordinates = points.map((p, i) => [padX + i / (points.length - 1) * (width - padX - 12), height - padY - (p.value - min) / span * (height - padY * 2 - (compact ? 0 : 18))]);
  const path = coordinates.map((p, i) => `${i ? 'L' : 'M'}${p[0]},${p[1]}`).join(' ');
  const chosen = hover === null ? points.length - 1 : hover;
  const date = (d: string) => new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: 'UTC' });
  return <div className={compact ? 'spark' : 'chart-wrap'}>
    {!compact && <div className="chart-readout"><span>{date(points[chosen].date)} · UTC</span><strong>{points[chosen].value.toLocaleString('en-US', { maximumFractionDigits: 2 })}<small> {unit}</small></strong></div>}
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${label}. ${points.length} observations; first ${points[0].value.toFixed(2)}, latest ${points.at(-1)!.value.toFixed(2)}. UTC.`} onMouseLeave={() => setHover(null)}>
      <defs><linearGradient id={id} x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity=".19" /><stop offset="100%" stopColor={color} stopOpacity="0" /></linearGradient></defs>
      {!compact && [0, 1, 2, 3].map(n => <g key={n}><line x1={padX} x2={width - 12} y1={padY + n * (height - 2 * padY - 18) / 3} y2={padY + n * (height - 2 * padY - 18) / 3} stroke="var(--border)" strokeDasharray="3 6" /><text x="0" y={padY + n * (height - 2 * padY - 18) / 3 + 5} fill="var(--muted)" fontSize="11">{(max - span * n / 3).toLocaleString('en', { notation: 'compact', maximumFractionDigits: 1 })}</text></g>)}
      <path d={`${path} L${width - 12},${height - padY} L${padX},${height - padY}Z`} fill={`url(#${id})`} />
      <path d={path} fill="none" stroke={color} strokeWidth={compact ? 2.2 : 2.5} strokeLinejoin="round" />
      {!compact && <><circle cx={coordinates[chosen][0]} cy={coordinates[chosen][1]} r="4" fill={color} /><line x1={coordinates[chosen][0]} x2={coordinates[chosen][0]} y1={padY} y2={height - padY} stroke={color} strokeOpacity=".2" />{[0, Math.floor(points.length / 2), points.length - 1].map(i => <text key={i} x={coordinates[i][0]} y={height - 1} textAnchor={i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'} fill="var(--muted)" fontSize="11">{date(points[i].date)}</text>)}<rect x={padX} y="0" width={width - padX} height={height - padY} fill="transparent" onMouseMove={e => { const box = e.currentTarget.getBoundingClientRect(); setHover(Math.min(points.length - 1, Math.max(0, Math.round((e.clientX - box.left) / box.width * (points.length - 1))))); }} /></>}
    </svg>
    {!compact && <span className="micro chart-note">Observed values • {unit} • UTC • no projected price path</span>}
  </div>;
}

const maturity: Record<string, number> = { Emerging: 10, 'Early Growth': 25, Accelerating: 35, Breakout: 48, Mainstream: 65, Mature: 80, Peaking: 88, Cooling: 76, Declining: 85, Dormant: 95, Resurgent: 20 };
export function Radar({ trends, onOpen }: { trends: Trend[]; onOpen: (id: string) => void }) {
  const [selected, setSelected] = useState<string | null>(null);
  return <><div className="radar"><div className="radar-label tl">EMERGING</div><div className="radar-label tr">MAINSTREAM</div><div className="radar-label bl">EARLY / QUIET</div><div className="radar-label br">COOLING</div><div className="radar-cross-x" /><div className="radar-cross-y" />{trends.filter(t => t.score.current_score !== undefined).map((t, i) => <button key={t.id} className={`radar-dot ${selected === t.id ? 'selected' : ''}`} style={{ left: `${9 + (maturity[t.score.lifecycle_stage || 'Mature'] ?? 50) * .82}%`, bottom: `${12 + (t.score.components?.momentum ?? 50) * .76}%`, width: `${11 + (t.score.components?.acceleration ?? 50) / 12}px`, height: `${11 + (t.score.components?.acceleration ?? 50) / 12}px`, background: ['var(--lime)', 'var(--cyan)', 'var(--violet)', 'var(--amber)'][i % 4] }} aria-label={`${t.name}, ${t.score.lifecycle_stage}, momentum ${t.score.components?.momentum}, confidence ${t.forecast?.confidence || 'unavailable'}`} title={`${t.name} · ${t.score.lifecycle_stage}`} onFocus={() => setSelected(t.id)} onMouseEnter={() => setSelected(t.id)} onClick={() => onOpen(t.id)} />)}<span className="radar-axis">MATURITY →</span><span className="radar-axis-y">MOMENTUM →</span></div><div className="radar-caption">{selected ? trends.find(t => t.id === selected)?.name : 'Select a signal to inspect its evidence'}<span>Size = acceleration · heuristic positions</span></div></>;
}
