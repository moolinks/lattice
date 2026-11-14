export function Sparkline({
  values,
  width = 110,
  height = 30,
  color = "var(--accent)",
}: {
  values: number[];
  width?: number;
  height?: number;
  color?: string;
}) {
  if (!values.length) return <div style={{ width, height }} />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const points = values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * (width - 4) + 2;
      const y = height - 3 - ((value - min) / range) * (height - 6);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const last = values[values.length - 1];
  const lastY = height - 3 - ((last - min) / range) * (height - 6);
  return (
    <svg width={width} height={height} className="sparkline" role="img" aria-label="趋势">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={width - 2} cy={lastY} r="2.4" fill={color} />
    </svg>
  );
}

export function ActivityBars({ values }: { values: { date: string; count: number }[] }) {
  const max = Math.max(...values.map((v) => v.count), 1);
  return (
    <div className="activity-bars" aria-label="最近七天活动">
      {values.map((item) => (
        <div className="activity-bar-col" key={item.date} title={`${item.date} · ${item.count} 次更新`}>
          <div className="activity-bar-track">
            <div
              className="activity-bar-fill"
              style={{ height: `${Math.max((item.count / max) * 100, 4)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
