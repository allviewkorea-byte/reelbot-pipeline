"use client"

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts"

interface ChartEntry {
  name: string
  revenue: number
  fill: string
}

interface RevenueChartProps {
  data: ChartEntry[]
}

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: { value: number }[]
  label?: string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 shadow-lg">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p
        className="text-sm font-bold text-foreground"
        style={{ fontFamily: "var(--font-geist-mono)" }}
      >
        ${payload[0].value}
      </p>
    </div>
  )
}

export function RevenueChart({ data }: RevenueChartProps) {
  return (
    <div className="flex gap-6">
      {/* Bar chart */}
      <div className="flex-1">
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data} barSize={36} margin={{ top: 4, right: 4, bottom: 0, left: -16 }}>
            <CartesianGrid
              strokeDasharray="3 3"
              vertical={false}
              stroke="hsl(217 32% 22%)"
            />
            <XAxis
              dataKey="name"
              tick={{ fill: "hsl(215 20% 65%)", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: "hsl(215 20% 65%)", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => `$${v}`}
            />
            <Tooltip
              content={<CustomTooltip />}
              cursor={{ fill: "hsl(217 32% 22% / 0.5)" }}
            />
            <Bar dataKey="revenue" radius={[4, 4, 0, 0]}>
              {data.map((entry, i) => (
                <Cell key={i} fill={entry.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <div className="flex flex-col justify-center gap-3 min-w-[120px]">
        {data.map((entry) => (
          <div key={entry.name} className="flex items-center gap-2">
            <div
              className="h-2.5 w-2.5 rounded-full shrink-0"
              style={{ backgroundColor: entry.fill }}
            />
            <div>
              <p className="text-xs text-muted-foreground leading-none">{entry.name}</p>
              <p
                className="text-sm font-bold text-foreground leading-tight mt-0.5"
                style={{ fontFamily: "var(--font-geist-mono)" }}
              >
                ${entry.revenue}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
