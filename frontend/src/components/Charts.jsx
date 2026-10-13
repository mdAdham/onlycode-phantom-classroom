import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'

export function PowerTrendChart({ data }) {
  return <ResponsiveContainer width="100%" height="100%">
    <AreaChart data={data} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
      <defs><linearGradient id="powerFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#28a779" stopOpacity={0.2} /><stop offset="95%" stopColor="#28a779" stopOpacity={0.01} /></linearGradient></defs>
      <CartesianGrid stroke="#edf0f2" vertical={false} />
      <XAxis dataKey="label" axisLine={false} tickLine={false} tick={{ fill: '#8b949f', fontSize: 11 }} minTickGap={36} />
      <YAxis axisLine={false} tickLine={false} tick={{ fill: '#8b949f', fontSize: 11 }} tickFormatter={(value) => value >= 1000 ? `${(value / 1000).toFixed(1)}k` : value} />
      <Tooltip formatter={(value) => [`${Math.round(value)} W`, 'Campus power']} contentStyle={{ border: '1px solid #e8ecef', borderRadius: 10, fontSize: 12 }} />
      <Area type="monotone" dataKey="power_watts" stroke="#219b70" strokeWidth={2.2} fill="url(#powerFill)" />
    </AreaChart>
  </ResponsiveContainer>
}

export function EnergyReadingsChart({ data }) {
  return <ResponsiveContainer width="100%" height="100%">
    <AreaChart data={data} margin={{ top: 10, right: 14, left: -16, bottom: 0 }}>
      <defs><linearGradient id="energyFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#4686dc" stopOpacity={0.2} /><stop offset="100%" stopColor="#4686dc" stopOpacity={0.01} /></linearGradient></defs>
      <CartesianGrid stroke="#edf0f2" vertical={false} />
      <XAxis dataKey="label" axisLine={false} tickLine={false} tick={{ fill: '#8b949f', fontSize: 11 }} minTickGap={30} />
      <YAxis axisLine={false} tickLine={false} tick={{ fill: '#8b949f', fontSize: 11 }} />
      <Tooltip formatter={(value) => [`${value} W`, 'Power']} />
      <Area type="monotone" dataKey="power_watts" stroke="#4b85d5" fill="url(#energyFill)" strokeWidth={2} />
    </AreaChart>
  </ResponsiveContainer>
}

export function ClassroomEnergyChart({ data }) {
  const colors = ['#2a9c70', '#5099d9', '#8bc6ac', '#e5aa4d']
  return <ResponsiveContainer width="100%" height="100%">
    <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
      <CartesianGrid stroke="#edf0f2" vertical={false} />
      <XAxis dataKey="classroom" axisLine={false} tickLine={false} tick={{ fill: '#83909b', fontSize: 10 }} />
      <YAxis axisLine={false} tickLine={false} tick={{ fill: '#83909b', fontSize: 10 }} />
      <Tooltip formatter={(value) => [`${value} kWh`, 'Energy']} />
      <Bar dataKey="energy_kwh" fill="#2a9c70" radius={[5, 5, 0, 0]} maxBarSize={40}>
        {data.map((item, index) => <Cell key={item.classroom_id} fill={colors[index % colors.length]} />)}
      </Bar>
    </BarChart>
  </ResponsiveContainer>
}
