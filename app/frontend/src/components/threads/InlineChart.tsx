import {
  ResponsiveContainer,
  LineChart,
  BarChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import type { ChartDataEvent } from "../../lib/types";

const COLORS = ["#8b5cf6", "#06b6d4", "#f59e0b", "#ef4444", "#10b981"];

function formatLabel(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatValue(value: unknown): string {
  if (typeof value !== "number") return String(value ?? "");
  if (Math.abs(value) >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
  if (Math.abs(value) >= 1e3) return `$${(value / 1e3).toFixed(0)}K`;
  return value.toLocaleString();
}

export function InlineChart({ chart }: { chart: ChartDataEvent }) {
  const { chart_type, x_key, y_keys, data } = chart;

  if (!data || data.length < 2 || !y_keys.length) return null;

  const ChartComponent = chart_type === "line" ? LineChart : BarChart;

  return (
    <div className="my-3 rounded-lg border border-border bg-card p-3">
      <ResponsiveContainer width="100%" height={220}>
        <ChartComponent data={data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
          <XAxis
            dataKey={x_key}
            tick={{ fontSize: 10 }}
            tickFormatter={(v) => String(v).length > 12 ? String(v).slice(0, 10) + "…" : String(v)}
          />
          <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => formatValue(v)} width={60} />
          <Tooltip
            formatter={(v: number) => formatValue(v)}
            labelFormatter={(label) => String(label)}
            contentStyle={{ fontSize: 11, borderRadius: 6 }}
          />
          {y_keys.length > 1 && (
            <Legend
              wrapperStyle={{ fontSize: 10 }}
              formatter={(value) => formatLabel(value)}
            />
          )}
          {chart_type === "line"
            ? y_keys.map((key, i) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={COLORS[i % COLORS.length]}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  name={formatLabel(key)}
                />
              ))
            : y_keys.map((key, i) => (
                <Bar
                  key={key}
                  dataKey={key}
                  fill={COLORS[i % COLORS.length]}
                  radius={[4, 4, 0, 0]}
                  name={formatLabel(key)}
                />
              ))}
        </ChartComponent>
      </ResponsiveContainer>
    </div>
  );
}
