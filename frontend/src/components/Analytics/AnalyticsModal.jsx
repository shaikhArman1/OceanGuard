import React from 'react';
import {
  BarChart, Bar, LineChart, Line, AreaChart, Area,
  PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts';
import { MONTHLY_STATS, SYSTEM_STATS, VESSELS, SPILLS } from '../../data/mockData';
import { FaTimes } from 'react-icons/fa';

const COLORS = ['#ff3a4e', '#ff8c00', '#f5c842', '#00d4ff', '#00e676'];

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'var(--bg-elevated)',
      border: '1px solid var(--border-dim)',
      borderRadius: 8,
      padding: '8px 12px',
      fontSize: 11,
      color: 'var(--text-primary)'
    }}>
      <div style={{ fontWeight: 700, marginBottom: 4, color: 'var(--text-secondary)' }}>{label}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {p.value}
        </div>
      ))}
    </div>
  );
};

// Vessel type distribution for pie chart
const vesselTypeDist = [
  { name: 'Crude Tanker', value: 8 },
  { name: 'Product Tanker', value: 6 },
  { name: 'Chemical Tanker', value: 4 },
  { name: 'Bulk Carrier', value: 3 },
  { name: 'Other', value: 1 },
];

// Detection confidence trend
const confidenceTrend = [
  { month: 'Jun', accuracy: 88.2 },
  { month: 'Jul', accuracy: 90.5 },
  { month: 'Aug', accuracy: 91.8 },
  { month: 'Sep', accuracy: 93.1 },
  { month: 'Oct', accuracy: 93.9 },
  { month: 'Nov', accuracy: 94.7 },
];

export default function AnalyticsModal({ onClose }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <div>
            <div className="modal-title">📊 Analytics & Intelligence Report</div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
              Indian Ocean Region · June–November 2024
            </div>
          </div>
          <button className="detail-close" onClick={onClose} style={{ position: 'static' }}>
            <FaTimes />
          </button>
        </div>

        {/* KPI Row */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 16 }}>
          {[
            { label: 'Total Spills Detected', value: SYSTEM_STATS.total_spills_detected, color: 'var(--critical)' },
            { label: 'Vessels Attributed', value: SYSTEM_STATS.vessels_identified, color: 'var(--high)' },
            { label: 'Detection Accuracy', value: `${SYSTEM_STATS.model_accuracy}%`, color: 'var(--cyan)' },
            { label: 'Avg. Response Time', value: `${SYSTEM_STATS.response_time_avg_min} min`, color: 'var(--success)' },
          ].map(kpi => (
            <div key={kpi.label} style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-dim)',
              borderRadius: 10,
              padding: '12px 14px',
              textAlign: 'center'
            }}>
              <div style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 24,
                fontWeight: 700,
                color: kpi.color
              }}>{kpi.value}</div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                {kpi.label}
              </div>
            </div>
          ))}
        </div>

        {/* Charts row 1 */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
          {/* Monthly spill bar chart */}
          <div className="chart-wrapper">
            <div className="chart-title">Monthly Spill Detections</div>
            <ResponsiveContainer width="100%" height={170}>
              <BarChart data={MONTHLY_STATS} barSize={14} barGap={3}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis dataKey="month" tick={{ fill: '#8fa3bf', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#8fa3bf', fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ fontSize: 10, color: '#8fa3bf' }} />
                <Bar dataKey="spills"   fill="#ff3a4e" name="Spills"   radius={[3,3,0,0]} />
                <Bar dataKey="resolved" fill="#00e676" name="Resolved" radius={[3,3,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Vessel type pie */}
          <div className="chart-wrapper">
            <div className="chart-title">Suspect Vessel Types</div>
            <ResponsiveContainer width="100%" height={170}>
              <PieChart>
                <Pie
                  data={vesselTypeDist}
                  cx="50%"
                  cy="50%"
                  innerRadius={40}
                  outerRadius={70}
                  paddingAngle={3}
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  labelLine={{ stroke: '#4d6580', strokeWidth: 1 }}
                >
                  {vesselTypeDist.map((entry, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="none" />
                  ))}
                </Pie>
                <Tooltip content={<CustomTooltip />} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Chart row 2 */}
        <div className="chart-wrapper">
          <div className="chart-title">Model Detection Accuracy Trend (%)</div>
          <ResponsiveContainer width="100%" height={130}>
            <AreaChart data={confidenceTrend}>
              <defs>
                <linearGradient id="accGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#00d4ff" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#00d4ff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis dataKey="month" tick={{ fill: '#8fa3bf', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis domain={[85, 100]} tick={{ fill: '#8fa3bf', fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="accuracy"
                stroke="#00d4ff"
                strokeWidth={2}
                fill="url(#accGrad)"
                name="Accuracy %"
                dot={{ fill: '#00d4ff', r: 3 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Bottom note */}
        <div style={{
          marginTop: 12,
          padding: '8px 12px',
          background: 'var(--bg-card)',
          borderRadius: 8,
          fontSize: 10,
          color: 'var(--text-muted)',
          borderLeft: '3px solid var(--cyan)'
        }}>
          <strong style={{ color: 'var(--cyan)' }}>SIH PS 26143</strong> — OceanGuard
          uses Sentinel-1 SAR imagery processed by a U-Net segmentation model (IoU: 0.947)
          combined with a weighted AIS attribution algorithm to identify vessels responsible for marine oil spills.
          Organization: <strong style={{ color: 'var(--text-secondary)' }}>NTRO</strong> · Theme: Space Technology
        </div>
      </div>
    </div>
  );
}
