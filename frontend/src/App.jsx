import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { BrowserRouter, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import {
  Activity, AlertTriangle, ArrowDownRight, Bell, Building2,
  CalendarDays, Check, CheckCircle2, CircleHelp, Clock3, Download,
  Fan, GraduationCap, LayoutDashboard, Lightbulb, LoaderCircle, Menu, QrCode,
  Search, ShieldCheck, Sparkles, Users, Zap, AirVent, X,
} from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { api, downloadReport } from './services/api'
import './App.css'

const PowerTrendChart = lazy(() => import('./components/Charts.jsx').then((module) => ({ default: module.PowerTrendChart })))
const EnergyReadingsChart = lazy(() => import('./components/Charts.jsx').then((module) => ({ default: module.EnergyReadingsChart })))
const ClassroomEnergyChart = lazy(() => import('./components/Charts.jsx').then((module) => ({ default: module.ClassroomEnergyChart })))
const QRScanner = lazy(() => import('./components/QRScanner.jsx'))

const navItems = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/attendance', label: 'Attendance', icon: Users },
  { to: '/classrooms', label: 'Classrooms', icon: Building2 },
  { to: '/energy', label: 'Energy monitoring', icon: Zap },
  { to: '/alerts', label: 'Alerts', icon: Bell },
  { to: '/reports', label: 'Reports', icon: Activity },
]

function usePageTitle() {
  const location = useLocation()
  return navItems.find((item) => item.to === location.pathname)?.label || 'Overview'
}

function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [toast, setToast] = useState(null)
  const [working, setWorking] = useState(false)
  const pageTitle = usePageTitle()

  useEffect(() => {
    if (!toast) return undefined
    const timeout = window.setTimeout(() => setToast(null), 4200)
    return () => window.clearTimeout(timeout)
  }, [toast])

  const resetDemo = async () => {
    if (!window.confirm('Reset the local demo database and restore its sample data?')) return
    setWorking(true)
    try {
      await api('/demo/reset', { method: 'POST', body: {} })
      setToast({ kind: 'success', text: 'Demo data reset successfully.' })
      window.location.reload()
    } catch (error) {
      setToast({ kind: 'error', text: error.message })
    } finally {
      setWorking(false)
    }
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`}>
        <div className="brand">
          <div className="brand-mark"><Zap size={19} fill="currentColor" /></div>
          <div><strong>campus<span>grid</span></strong><small>SMART ENERGY</small></div>
          <button className="icon-button sidebar-close" onClick={() => setMenuOpen(false)} aria-label="Close navigation"><X size={18} /></button>
        </div>
        <div className="workspace-label">WORKSPACE</div>
        <nav className="side-nav">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} onClick={() => setMenuOpen(false)}>
              <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
              {label === 'Alerts' && <span className="nav-dot" />}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-spacer" />
        <div className="sidebar-note">
          <div className="note-icon"><Sparkles size={16} /></div>
          <strong>Demo environment</strong>
          <p>Readings are simulated for this campus preview.</p>
          <span className="online-indicator"><i /> System operational</span>
        </div>
        <div className="profile">
          <div className="avatar">AD</div>
          <div className="profile-copy"><strong>Campus Admin</strong><small>Facilities team</small></div>
          <CircleHelp size={17} className="profile-help" />
        </div>
      </aside>
      {menuOpen && <button className="sidebar-backdrop" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}
      <main className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <button className="icon-button menu-toggle" onClick={() => setMenuOpen(true)} aria-label="Open navigation"><Menu size={20} /></button>
            <div className="breadcrumbs"><span>Campus</span><b>/</b><strong>{pageTitle}</strong></div>
          </div>
          <div className="topbar-actions">
            <span className="live-pill"><i /> LIVE DEMO</span>
            <button className="button button-quiet reset-button" onClick={resetDemo} disabled={working}>
              {working ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />} Reset demo
            </button>
            <button className="icon-button topbar-bell" onClick={() => { window.location.href = '/alerts' }} aria-label="View alerts"><Bell size={18} /><i /></button>
            <div className="avatar avatar-small">AD</div>
          </div>
        </header>
        <div className="page-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/attendance" element={<AttendancePage notify={setToast} />} />
            <Route path="/classrooms" element={<ClassroomsPage />} />
            <Route path="/energy" element={<EnergyPage notify={setToast} />} />
            <Route path="/alerts" element={<AlertsPage notify={setToast} />} />
            <Route path="/reports" element={<ReportsPage notify={setToast} />} />
            <Route path="*" element={<Dashboard />} />
          </Routes>
        </div>
      </main>
      {toast && <div className={`toast toast-${toast.kind}`} role="status"><span>{toast.kind === 'success' ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}</span>{toast.text}<button onClick={() => setToast(null)} aria-label="Dismiss"><X size={16} /></button></div>}
    </div>
  )
}

function PageHeading({ eyebrow, title, description, children }) {
  return <div className="page-heading">
    <div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>
    {children && <div className="heading-actions">{children}</div>}
  </div>
}

function Loading() {
  return <div className="loading-state"><LoaderCircle className="spin" size={22} /><span>Loading campus data…</span></div>
}

function ErrorState({ error, retry }) {
  return <div className="error-state"><AlertTriangle size={20} /><div><strong>Couldn’t load this data</strong><p>{error}</p></div>{retry && <button className="button button-outline" onClick={retry}>Try again</button>}</div>
}

function EmptyState({ title, detail }) {
  return <div className="empty-state"><div className="empty-icon"><Activity size={19} /></div><strong>{title}</strong><p>{detail}</p></div>
}

function StatCard({ label, value, unit, icon: Icon, tone = 'blue', hint, trend }) {
  return <article className="stat-card">
    <div className="stat-top"><span>{label}</span><div className={`stat-icon ${tone}`}><Icon size={18} strokeWidth={1.8} /></div></div>
    <div className="stat-value">{value}<small>{unit}</small></div>
    <div className="stat-foot">{trend && <span className="trend-up"><ArrowDownRight size={14} /> {trend}</span>}<span>{hint}</span></div>
  </article>
}

function StatusBadge({ children, tone = 'neutral' }) {
  return <span className={`status-badge status-${tone}`}><i />{children}</span>
}

const power = (watts) => watts >= 1000 ? `${(watts / 1000).toFixed(1)} kW` : `${Math.round(watts || 0)} W`
const dateTime = (value) => value ? new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '—'
const roomTone = (room) => room.wastage_status === 'Alert' ? 'danger' : room.occupancy_status === 'Occupied' ? 'blue' : room.occupancy_status === 'Awaiting occupancy confirmation' ? 'warning' : 'green'

function Dashboard() {
  const [data, setData] = useState(null)
  const [trend, setTrend] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [roomFilter, setRoomFilter] = useState('')
  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [summary, energyTrend] = await Promise.all([api('/dashboard'), api('/dashboard/energy-trend')])
      setData(summary)
      setTrend(energyTrend)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => {
    const timer = window.setTimeout(() => { void load() }, 0)
    return () => window.clearTimeout(timer)
  }, [load])
  const visibleRooms = useMemo(() => (data?.classrooms || []).filter((room) => !roomFilter || room.room_code === roomFilter), [data, roomFilter])

  if (loading) return <Loading />
  if (error && !data) return <ErrorState error={error} retry={load} />
  return <>
    <PageHeading eyebrow="CAMPUS STATUS" title="Campus overview" description="A clear picture of attendance, classroom activity and energy use across campus.">
      <div className="updated-label"><span className="live-mini" /> Live campus data</div>
    </PageHeading>
    {error && <ErrorState error={error} retry={load} />}
    <div className="stats-grid">
      <StatCard label="Classrooms" value={data.classroom_count} icon={Building2} tone="blue" hint="Across 4 departments" />
      <StatCard label="Students present" value={data.present_count} icon={Users} tone="green" hint="In active class sessions" />
      <StatCard label="Campus power" value={power(data.current_power_watts)} icon={Zap} tone="amber" hint="Latest simulated readings" />
      <StatCard label="Active alerts" value={data.active_alert_count} icon={Bell} tone={data.active_alert_count ? 'red' : 'green'} hint="Requires facilities attention" />
    </div>
    <div className="dashboard-grid">
      <section className="panel trend-panel">
        <div className="panel-heading"><div><h2>Energy consumption</h2><p>Campus power draw throughout the last 24 hours</p></div><span className="chart-legend"><i /> Power draw <span className="demo-tag">SIMULATED</span></span></div>
        <div className="chart-wrap">
          {trend.length ? <Suspense fallback={<Loading />}><PowerTrendChart data={trend} /></Suspense> : <EmptyState title="No energy history yet" detail="Add simulated readings to see a trend." />}
        </div>
        <div className="chart-footer"><span>Energy use varies with class schedules and occupancy.</span><span><Clock3 size={13} /> Updated just now</span></div>
      </section>
      <section className="panel savings-panel">
        <div className="panel-heading"><div><h2>Potential savings</h2><p>From confirmed empty-room incidents</p></div><div className="panel-icon green-icon"><Lightbulb size={17} /></div></div>
        <div className="savings-amount">₹{Number(data.potential_savings_inr).toFixed(2)}</div>
        <div className="savings-caption">Estimated potential cost savings</div>
        <div className="savings-divider" />
        <div className="savings-kwh"><span>Estimated avoidable energy</span><strong>{Number(data.estimated_avoidable_kwh).toFixed(3)} <small>kWh</small></strong></div>
        <div className="savings-rate"><span>Illustrative tariff</span><strong>₹{data.tariff_inr_per_kwh}/kWh</strong></div>
        <div className="estimate-note"><CircleHelp size={14} /><span>Potential estimate only — not verified savings.</span></div>
      </section>
    </div>
    <div className="dashboard-grid lower-grid">
      <section className="panel rooms-panel">
        <div className="panel-heading"><div><h2>Classroom status</h2><p>Occupancy and latest power readings</p></div><div className="panel-heading-right"><select className="compact-select" value={roomFilter} onChange={(event) => setRoomFilter(event.target.value)}><option value="">All classrooms</option>{data.classrooms.map((room) => <option key={room.id} value={room.room_code}>{room.room_code}</option>)}</select><NavLink className="text-link" to="/classrooms">View all <span>→</span></NavLink></div></div>
        <div className="room-list">
          {visibleRooms.slice(0, 5).map((room) => <div className="room-row" key={room.id}>
            <div className="room-avatar"><Building2 size={16} /></div><div className="room-name"><strong>{room.room_code}</strong><small>{room.department}</small></div>
            <div className="room-occupancy"><span>{room.occupancy} / {room.capacity}</span><div className="mini-progress"><i style={{ width: `${Math.min(100, room.occupancy / room.capacity * 100)}%` }} /></div></div>
            <div className="room-power"><Zap size={14} />{power(room.power_watts)}</div>
            <StatusBadge tone={roomTone(room)}>{room.occupancy_status === 'Awaiting occupancy confirmation' ? 'Awaiting' : room.wastage_status === 'Alert' ? 'Wastage' : room.occupancy_status === 'Occupied' ? 'In session' : room.occupancy_status === 'Confirmed empty' ? 'Confirmed empty' : 'No session'}</StatusBadge>
          </div>)}
          {!visibleRooms.length && <EmptyState title="No classrooms match" detail="Choose another classroom filter." />}
        </div>
      </section>
      <section className="panel alerts-panel">
        <div className="panel-heading"><div><h2>Recent alerts</h2><p>Latest facilities notifications</p></div><NavLink className="text-link" to="/alerts">All alerts <span>→</span></NavLink></div>
        {data.recent_alerts.length ? <div className="recent-alert-list">{data.recent_alerts.slice(0, 4).map((alert) => <div className="recent-alert" key={alert.id}>
          <div className={`alert-mark ${alert.status === 'resolved' ? 'resolved' : 'warning'}`}>{alert.status === 'resolved' ? <Check size={15} /> : <AlertTriangle size={15} />}</div>
          <div className="recent-alert-copy"><strong>{alert.classroom} · {alert.status === 'resolved' ? 'Resolved' : alert.type}</strong><p>{alert.message}</p><small>{dateTime(alert.created_at)}</small></div>
        </div>)}</div> : <EmptyState title="All clear" detail="No alerts have been raised." />}
      </section>
    </div>
  </>
}

function AttendancePage({ notify }) {
  const [sessions, setSessions] = useState([])
  const [selected, setSelected] = useState('')
  const [students, setStudents] = useState([])
  const [studentSearch, setStudentSearch] = useState('')
  const [studentId, setStudentId] = useState('')
  const [token, setToken] = useState(null)
  const [method, setMethod] = useState('manual')
  const [records, setRecords] = useState([])
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)
  const [camera, setCamera] = useState(false)
  const session = sessions.find((item) => item.id === Number(selected))

  const loadSessions = useCallback(async () => {
    try {
      const active = await api('/sessions?status=active')
      setSessions(active)
      setSelected((current) => active.some((item) => String(item.id) === current) ? current : String(active[0]?.id || ''))
    } catch (error) { notify({ kind: 'error', text: error.message }) }
  }, [notify])

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadSessions() }, 0)
    return () => window.clearTimeout(timer)
  }, [loadSessions])
  useEffect(() => {
    let cancelled = false
    if (!selected) return undefined
    api(`/attendance/session/${selected}`).then((result) => { if (!cancelled) setRecords(result.records) }).catch((error) => notify({ kind: 'error', text: error.message }))
    return () => { cancelled = true }
  }, [selected, notify])
  useEffect(() => {
    let cancelled = false
    if (studentSearch.trim().length < 2) return undefined
    const timer = window.setTimeout(() => api(`/students?search=${encodeURIComponent(studentSearch.trim())}`).then((result) => { if (!cancelled) setStudents(result.slice(0, 6)) }).catch(() => setStudents([])), 250)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [studentSearch])

  const generateQr = async () => {
    if (!selected) return
    setBusy(true)
    try {
      const generated = await api(`/sessions/${selected}/qr`, { method: 'POST', body: {} })
      setToken(generated)
      return generated
    }
    catch (error) { notify({ kind: 'error', text: error.message }) }
    finally { setBusy(false) }
  }
  const mark = async (method = 'manual') => {
    setMessage(null)
    if (!selected || !studentId.trim()) { setMessage({ kind: 'error', text: 'Choose a session and enter a registered student ID.' }); return }
    if (!token?.token) { setMessage({ kind: 'error', text: 'Generate the session QR token before marking attendance.' }); return }
    setBusy(true)
    try {
      const result = await api('/attendance/mark', { method: 'POST', body: { session_id: Number(selected), student_id: studentId.trim(), token: token.token, method } })
      setMessage({ kind: 'success', text: `${result.student.name} marked present. Occupancy is now ${result.occupancy} of ${result.capacity}.` })
      setStudentId('')
      setStudentSearch('')
      const updated = await api(`/attendance/session/${selected}`)
      setRecords(updated.records)
      setMethod('manual')
      notify({ kind: 'success', text: 'Attendance recorded successfully.' })
    } catch (error) { setMessage({ kind: 'error', text: error.message }) }
    finally { setBusy(false) }
  }
  const toggleCamera = async () => {
    if (camera) { setCamera(false); return }
    const sessionToken = token || await generateQr()
    if (!sessionToken) return
    setCamera(true)
  }
  return <>
    <PageHeading eyebrow="PRESENCE & PARTICIPATION" title="Attendance" description="Verify presence against an active class session using a secure session QR token." />
    <div className="attendance-layout">
      <section className="panel attendance-form-panel">
        <div className="panel-heading"><div><h2>Mark attendance</h2><p>Session-specific verification with manual ID fallback</p></div><div className="panel-icon blue-icon"><QrCode size={17} /></div></div>
        <label className="field-label" htmlFor="session-select">Active class session</label>
        <select id="session-select" className="form-control" value={selected} onChange={(event) => { setSelected(event.target.value); setToken(null); setMethod('manual'); setMessage(null); setRecords([]) }}>
          {!sessions.length && <option value="">No active sessions available</option>}
          {sessions.map((item) => <option value={item.id} key={item.id}>{item.classroom} · {item.subject} ({item.attendance_count} present)</option>)}
        </select>
        {session && <div className="session-summary"><div><span>CLASSROOM</span><strong>{session.classroom}</strong></div><div><span>SESSION</span><strong>{session.subject}</strong></div><div><span>VERIFIED</span><strong>{records.length} students</strong></div></div>}
        <div className="qr-section">
          <div className="qr-copy"><strong>Session QR token</strong><p>Token expires after 15 minutes. Generate a new one when needed.</p></div>
          {!token ? <button className="button button-outline" disabled={!session || busy} onClick={generateQr}>{busy ? <LoaderCircle className="spin" size={15} /> : <QrCode size={15} />} Generate QR</button> : <div className="qr-display"><QRCodeSVG value={JSON.stringify({ session_id: token.session_id, token: token.token })} size={132} level="M" /><div><span><CheckCircle2 size={14} />{token.expires_at ? `Expires ${dateTime(token.expires_at)}` : 'Session QR scanned'}</span><button className="text-link" onClick={generateQr}>Regenerate QR</button></div></div>}
        </div>
        <div className="divider-label"><span>OR ENTER STUDENT ID</span></div>
        <label className="field-label" htmlFor="student-search">Find a registered student</label>
        <div className="search-field"><Search size={16} /><input id="student-search" value={studentSearch} onChange={(event) => { setStudentSearch(event.target.value); setStudentId(event.target.value) }} placeholder="Search by name or student ID" /><span className="search-hint">⌘ K</span></div>
        {students.length > 0 && studentSearch.trim().length >= 2 && <div className="student-suggestions">{students.map((student) => <button key={student.id} onClick={() => { setStudentId(student.student_id); setStudentSearch(`${student.name} · ${student.student_id}`); setStudents([]) }}><span className="student-avatar">{student.name.split(' ').map((name) => name[0]).join('').slice(0, 2)}</span><span><strong>{student.name}</strong><small>{student.student_id} · {student.department}</small></span></button>)}</div>}
        <div className="attendance-input-row"><input className="form-control" value={studentId} onChange={(event) => { setStudentId(event.target.value); setStudentSearch(event.target.value) }} placeholder="Student ID (e.g. STU-009)" /><button className="button button-primary" disabled={!session || busy} onClick={() => mark(method)}>{busy ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />} Mark present</button></div>
        {message && <div className={`inline-message ${message.kind}`}><span>{message.kind === 'success' ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}</span>{message.text}</div>}
        <div className="attendance-actions"><button className="button button-quiet" disabled={!session || busy} onClick={toggleCamera}><QrCode size={15} />{camera ? 'Close scanner' : 'Scan QR with camera'}</button><span>Camera access requires localhost or HTTPS.</span></div>
        {camera && <Suspense fallback={<Loading />}><QRScanner sessionId={selected} onResult={(scannedToken) => { setToken({ session_id: Number(selected), token: scannedToken }); setMethod('qr'); setMessage({ kind: 'success', text: 'Session QR verified. Enter the student ID to complete attendance.' }); setCamera(false) }} onError={(text) => setMessage({ kind: 'error', text })} /></Suspense>}
        {session && <button className="session-complete-link" onClick={async () => {
          try {
            await api(`/sessions/${selected}`, { method: 'PATCH', body: { status: 'completed' } })
            setToken(null)
            setRecords([])
            await loadSessions()
            notify({ kind: 'success', text: 'Session completed. Room can now be confirmed empty.' })
          }
          catch (error) { notify({ kind: 'error', text: error.message }) }
        }}>Complete this session <span>→</span></button>}
      </section>
      <section className="panel attendance-records-panel">
        <div className="panel-heading"><div><h2>Session attendance</h2><p>{session ? `${session.classroom} · ${session.subject}` : 'Choose an active session'}</p></div><span className="record-count">{records.length} <small>verified</small></span></div>
        <div className="records-table-wrap"><table className="data-table"><thead><tr><th>STUDENT</th><th>METHOD</th><th>TIME</th></tr></thead><tbody>
          {records.map((record) => <tr key={record.id}><td><div className="person-cell"><span className="student-avatar">{record.student.name.split(' ').map((name) => name[0]).join('').slice(0, 2)}</span><span><strong>{record.student.name}</strong><small>{record.student.student_id}</small></span></div></td><td><span className="method-tag">{record.method === 'qr' ? <QrCode size={12} /> : <Check size={12} />}{record.method}</span></td><td>{dateTime(record.marked_at)}</td></tr>)}
        </tbody></table>
        {!records.length && <EmptyState title="No attendance records" detail={session ? 'Mark the first student present for this session.' : 'There are no active class sessions.'} />}
        </div>
        <div className="records-foot"><ShieldCheck size={15} /><span>Verified records are unique per student and class session.</span></div>
      </section>
    </div>
  </>
}

function ClassroomsPage() {
  const [rooms, setRooms] = useState([])
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(null)
  const [details, setDetails] = useState(null)
  const [error, setError] = useState('')
  const load = useCallback(() => api('/classrooms').then(setRooms).catch((requestError) => setError(requestError.message)), [])
  useEffect(() => {
    const timer = window.setTimeout(() => { void load() }, 0)
    return () => window.clearTimeout(timer)
  }, [load])
  const filtered = rooms.filter((room) => `${room.room_code} ${room.department} ${room.responsible_staff}`.toLowerCase().includes(query.toLowerCase()))
  const openDetails = async (room) => {
    setSelected(room.id)
    try { setDetails(await api(`/classrooms/${room.id}`)) } catch (requestError) { setError(requestError.message) }
  }
  return <>
    <PageHeading eyebrow="CAMPUS DIRECTORY" title="Classrooms" description="Room occupancy, active sessions and the latest connected energy readings.">
      <div className="directory-count"><Building2 size={16} /> {rooms.length} spaces</div>
    </PageHeading>
    {error && <ErrorState error={error} retry={load} />}
    <div className="toolbar panel"><div className="search-field toolbar-search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search rooms, departments or staff" /></div><span className="toolbar-summary">{filtered.length} classrooms</span></div>
    <div className="classroom-grid">
      {filtered.map((room) => <article className={`classroom-card ${selected === room.id ? 'classroom-selected' : ''}`} key={room.id}>
        <div className="classroom-card-top"><div className="classroom-symbol"><Building2 size={18} /></div><StatusBadge tone={roomTone(room)}>{room.wastage_status === 'Alert' ? 'Wastage alert' : room.session_status === 'active' ? 'Session active' : room.occupancy_status === 'Awaiting occupancy confirmation' ? 'Awaiting confirmation' : room.occupancy_status === 'Confirmed empty' ? 'Confirmed empty' : 'No active session'}</StatusBadge></div>
        <div className="classroom-title"><h2>{room.room_code}</h2><span>{room.department}</span></div>
        <div className="classroom-card-stats"><div><span>OCCUPANCY</span><strong>{room.occupancy}<small> / {room.capacity}</small></strong></div><div><span>POWER DRAW</span><strong>{power(room.power_watts)}</strong></div></div>
        <div className="appliance-line"><span><Lightbulb size={14} /> Lights <i className={room.lights_on ? 'appliance-on' : ''}>{room.lights_on ? 'On' : 'Off'}</i></span><span><Fan size={14} /> Fans <i className={room.fans_on ? 'appliance-on' : ''}>{room.fans_on ? 'On' : 'Off'}</i></span><span><AirVent size={14} /> AC <i className={room.ac_on ? 'appliance-on' : ''}>{room.ac_on ? 'On' : 'Off'}</i></span></div>
        <div className="classroom-card-bottom"><span><Users size={14} /> {room.responsible_staff}</span><button className="text-link" onClick={() => openDetails(room)}>Room details <span>→</span></button></div>
      </article>)}
      {!filtered.length && <div className="panel full-width"><EmptyState title="No classrooms found" detail="Adjust the search to find a campus space." /></div>}
    </div>
    {selected && <div className="modal-backdrop" onClick={() => { setSelected(null); setDetails(null) }}><section className="detail-modal panel" onClick={(event) => event.stopPropagation()}>
      <div className="modal-header"><div><div className="eyebrow">CLASSROOM DETAILS</div><h2>{details?.room_code || 'Loading room…'}</h2></div><button className="icon-button" onClick={() => { setSelected(null); setDetails(null) }} aria-label="Close"><X size={19} /></button></div>
      {!details ? <Loading /> : <><p className="modal-subtitle">{details.department} · Capacity {details.capacity} · {details.responsible_staff}</p><div className="modal-section"><h3>Recent energy readings</h3><div className="modal-reading-list">{details.readings.slice(0, 8).map((reading) => <div key={reading.id}><span>{dateTime(reading.recorded_at)} <em>{reading.source}</em></span><strong>{power(reading.power_watts)}</strong></div>)}</div></div><div className="modal-section"><h3>Class sessions</h3>{details.sessions.map((item) => <div className="session-detail-row" key={item.id}><span>{item.subject}<small>{dateTime(item.start_time)}</small></span><StatusBadge tone={item.status === 'active' ? 'blue' : item.status === 'completed' ? 'green' : 'warning'}>{item.status}</StatusBadge></div>)}</div></>}
    </section></div>}
  </>
}

function EnergyPage({ notify }) {
  const [rooms, setRooms] = useState([])
  const [readings, setReadings] = useState([])
  const [selected, setSelected] = useState('')
  const [watts, setWatts] = useState(420)
  const [ruleSettings, setRuleSettings] = useState(null)
  const [confirmEmpty, setConfirmEmpty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const load = useCallback(async () => {
    try {
      const [classrooms, latest, dashboard] = await Promise.all([api('/classrooms'), api('/energy/readings?limit=60'), api('/dashboard')])
      setError('')
      setRooms(classrooms)
      setReadings(latest)
      setRuleSettings(dashboard)
      setSelected((current) => current || String(classrooms.find((room) => room.session_status !== 'active')?.id || classrooms[0]?.id || ''))
    } catch (requestError) { setError(requestError.message) }
  }, [])
  useEffect(() => {
    const timer = window.setTimeout(() => { void load() }, 0)
    return () => window.clearTimeout(timer)
  }, [load])
  const simulateReading = async () => {
    if (!selected) return
    setBusy(true)
    try {
      const result = await api('/energy/simulate', { method: 'POST', body: { classroom_id: Number(selected), power_watts: Number(watts), count: 1 } })
      notify({ kind: 'success', text: result.incident_detected ? 'Wastage incident updated.' : 'Simulated energy reading added.' })
      await load()
    } catch (requestError) { notify({ kind: 'error', text: requestError.message }) }
    finally { setBusy(false) }
  }
  const simulateWaste = async () => {
    if (!selected || !confirmEmpty) { notify({ kind: 'error', text: 'Select a room and confirm that it is empty before simulating wastage.' }); return }
    setBusy(true)
    try {
      const result = await api('/demo/simulate-empty-room-wastage', { method: 'POST', body: { classroom_id: Number(selected), confirm_empty: true, power_watts: Number(watts) } })
      notify({ kind: 'success', text: result.incident_detected ? `${result.classroom}: incident raised at ${watts} W.` : 'Readings added. Detection duration has not yet been reached.' })
      setConfirmEmpty(false)
      await load()
    } catch (requestError) { notify({ kind: 'error', text: requestError.message }) }
    finally { setBusy(false) }
  }
  const chartData = [...readings].reverse().map((reading) => ({ ...reading, label: new Date(reading.recorded_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) }))
  const selectedRoom = rooms.find((room) => room.id === Number(selected))
  return <>
    <PageHeading eyebrow="METERING & SIMULATION" title="Energy monitoring" description="Explore campus power usage and run a safe, simulated empty-room demonstration.">
      <span className="demo-tag">SIMULATED FEED</span>
    </PageHeading>
    {error && <ErrorState error={error} retry={load} />}
    <div className="energy-banner"><div className="banner-icon"><Zap size={18} /></div><div><strong>Demo readings, not live smart-meter data</strong><p>Power and savings estimates use simulated samples. No appliances are controlled by this prototype.</p></div><span className="banner-demo-dot" /></div>
    <div className="energy-layout">
      <section className="panel energy-chart-panel"><div className="panel-heading"><div><h2>Recent power readings</h2><p>Latest campus samples · watts</p></div><span className="chart-legend"><i /> Simulated power</span></div><div className="energy-chart">
        {chartData.length ? <Suspense fallback={<Loading />}><EnergyReadingsChart data={chartData} /></Suspense> : <EmptyState title="No readings available" detail="Add a simulated reading to populate this chart." />}
      </div></section>
      <section className="panel simulation-panel"><div className="panel-heading"><div><h2>Run a simulation</h2><p>Generate a reading or trigger a wastage incident</p></div><div className="panel-icon amber-icon"><Activity size={17} /></div></div>
        <label className="field-label" htmlFor="energy-room">Classroom</label><select id="energy-room" className="form-control" value={selected} onChange={(event) => setSelected(event.target.value)}>{rooms.map((room) => <option value={room.id} key={room.id}>{room.room_code} · {room.occupancy_status}</option>)}</select>
        <label className="field-label" htmlFor="power-input">Power reading <span>(watts)</span></label><div className="number-input"><input id="power-input" type="number" min="0" max="20000" value={watts} onChange={(event) => setWatts(event.target.value)} /><span>W</span></div>
        <button className="button button-outline full-button" onClick={simulateReading} disabled={busy || !selected}>{busy ? <LoaderCircle className="spin" size={15} /> : <Activity size={15} />} Add simulated reading</button>
        <div className="simulation-divider" />
        <div className="demo-rule"><span className="rule-icon"><AlertTriangle size={16} /></span><div><strong>Empty-room wastage rule</strong><p>Confirmed empty + above {ruleSettings?.energy_threshold_watts ?? 'configured'} W for {ruleSettings?.demo_duration_seconds ?? 'a sustained'} seconds.</p></div></div>
        <label className="confirm-check"><input type="checkbox" checked={confirmEmpty} onChange={(event) => setConfirmEmpty(event.target.checked)} /><span>I confirm {selectedRoom?.room_code || 'this classroom'} is empty for this demo.</span></label>
        <button className="button button-danger full-button" onClick={simulateWaste} disabled={busy || !selected}>{busy ? <LoaderCircle className="spin" size={15} /> : <Zap size={15} />} Simulate empty-room wastage</button>
        <p className="simulation-footnote">Threshold and duration are illustrative prototype settings, not energy standards.</p>
      </section>
    </div>
    <section className="panel readings-panel"><div className="panel-heading"><div><h2>Latest readings</h2><p>Individual appliance state is simulated with each sample</p></div><span className="record-count">{readings.length} <small>samples</small></span></div>
      <div className="records-table-wrap"><table className="data-table"><thead><tr><th>CLASSROOM</th><th>POWER</th><th>APPLIANCES</th><th>SOURCE</th><th>RECORDED</th></tr></thead><tbody>{readings.slice(0, 12).map((item) => <tr key={item.id}><td><strong>{item.classroom}</strong></td><td><strong>{power(item.power_watts)}</strong></td><td><span className="appliance-table"><Lightbulb size={13} className={item.lights_on ? 'is-on' : ''} /><Fan size={13} className={item.fans_on ? 'is-on' : ''} /><AirVent size={13} className={item.ac_on ? 'is-on' : ''} /></span></td><td><span className="source-badge">{item.source}</span></td><td>{dateTime(item.recorded_at)}</td></tr>)}</tbody></table>{!readings.length && <EmptyState title="No recent readings" detail="The demo seed or simulation will add readings here." />}</div>
    </section>
  </>
}

function AlertsPage({ notify }) {
  const [alerts, setAlerts] = useState([])
  const [filter, setFilter] = useState('all')
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState(null)
  const load = useCallback(async () => {
    try { setAlerts(await api('/alerts')); setError('') } catch (requestError) { setError(requestError.message) }
  }, [])
  useEffect(() => {
    const timer = window.setTimeout(() => { void load() }, 0)
    return () => window.clearTimeout(timer)
  }, [load])
  const filtered = alerts.filter((alert) => filter === 'all' || (filter === 'active' ? alert.status !== 'resolved' : alert.status === 'resolved'))
  const update = async (alert, status) => {
    setBusyId(alert.id)
    try { await api(`/alerts/${alert.id}`, { method: 'PATCH', body: { status } }); notify({ kind: 'success', text: status === 'resolved' ? 'Alert resolved.' : 'Alert acknowledged.' }); await load() }
    catch (requestError) { notify({ kind: 'error', text: requestError.message }) }
    finally { setBusyId(null) }
  }
  return <>
    <PageHeading eyebrow="FACILITIES RESPONSE" title="Alerts" description="Review and resolve unusual energy use in confirmed empty spaces.">
      <div className="active-count"><span />{alerts.filter((alert) => alert.status !== 'resolved').length} active</div>
    </PageHeading>
    {error && <ErrorState error={error} retry={load} />}
    <div className="alert-overview">
      <div className="alert-overview-icon"><AlertTriangle size={19} /></div>
      <div><strong>Rule-based detection is active</strong><p>Alerts require confirmed room emptiness and power above the configured prototype threshold for a sustained duration.</p></div>
      <span className="demo-tag">DEMO RULE</span>
    </div>
    <div className="filter-tabs"><button className={filter === 'all' ? 'selected' : ''} onClick={() => setFilter('all')}>All alerts <span>{alerts.length}</span></button><button className={filter === 'active' ? 'selected' : ''} onClick={() => setFilter('active')}>Active <span>{alerts.filter((alert) => alert.status !== 'resolved').length}</span></button><button className={filter === 'resolved' ? 'selected' : ''} onClick={() => setFilter('resolved')}>Resolved <span>{alerts.filter((alert) => alert.status === 'resolved').length}</span></button></div>
    <div className="alert-list">{filtered.map((alert) => <article className="alert-card panel" key={alert.id}>
      <div className={`alert-type-icon ${alert.status === 'resolved' ? 'resolved' : alert.severity}`}><AlertTriangle size={18} /></div>
      <div className="alert-main"><div className="alert-title-line"><h2>{alert.classroom} <span>·</span> {alert.type}</h2><StatusBadge tone={alert.status === 'resolved' ? 'green' : alert.status === 'acknowledged' ? 'blue' : alert.severity === 'high' ? 'danger' : 'warning'}>{alert.status}</StatusBadge></div>
        <p>{alert.message}</p>
        <div className="alert-meta"><span><Building2 size={13} />{alert.department}</span><span><Users size={13} />{alert.occupancy_status} · {alert.occupancy} present</span><span><CalendarDays size={13} />{alert.session_status} session</span><span><Zap size={13} />{power(alert.detected_power_watts)}</span><span><Clock3 size={13} />{dateTime(alert.created_at)}</span></div>
        <div className="recommended-action"><Lightbulb size={14} /><span><strong>Recommended:</strong> {alert.recommended_action}</span></div>
      </div>
      {alert.status !== 'resolved' && <div className="alert-actions">{alert.status === 'open' && <button className="button button-outline" disabled={busyId === alert.id} onClick={() => update(alert, 'acknowledged')}>{busyId === alert.id ? <LoaderCircle className="spin" size={14} /> : <Check size={14} />} Acknowledge</button>}<button className="button button-primary" disabled={busyId === alert.id} onClick={() => update(alert, 'resolved')}>{busyId === alert.id ? <LoaderCircle className="spin" size={14} /> : <CheckCircle2 size={14} />} Resolve</button></div>}
    </article>)}{!filtered.length && <section className="panel"><EmptyState title="No alerts in this view" detail={filter === 'active' ? 'No active facilities issues. Nice work.' : 'Alerts will appear here when the energy rule is triggered.'} /></section>}</div>
  </>
}

function ReportsPage({ notify }) {
  const [range, setRange] = useState({ start: '', end: '' })
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const today = new Date()
      const end = today.toISOString().slice(0, 10)
      const start = new Date(today.getTime() - 7 * 86400000).toISOString().slice(0, 10)
      setRange({ start, end })
    }, 0)
    return () => window.clearTimeout(timer)
  }, [])
  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (range.start && range.end) {
        params.set('start', `${range.start}T00:00:00Z`)
        params.set('end', `${range.end}T23:59:59Z`)
      }
      setReport(await api(`/reports/energy${params.size ? `?${params}` : ''}`))
      setError('')
    } catch (requestError) { setError(requestError.message) }
    finally { setLoading(false) }
  }, [range])
  useEffect(() => {
    const timer = window.setTimeout(() => { void load() }, 0)
    return () => window.clearTimeout(timer)
  }, [load])
  const exportCsv = async () => {
    try { await downloadReport(`/reports/energy/export?start=${range.start}T00:00:00Z&end=${range.end}T23:59:59Z`) }
    catch (requestError) { notify({ kind: 'error', text: requestError.message }) }
  }
  const chart = report?.classrooms.filter((room) => room.energy_kwh > 0) || []
  return <>
    <PageHeading eyebrow="CAMPUS PERFORMANCE" title="Energy reports" description="Review consumption and potential avoidable energy across a selected period.">
      <button className="button button-outline" onClick={exportCsv} disabled={!range.start || !range.end}><Download size={15} /> Export CSV</button>
    </PageHeading>
    <div className="report-filters panel"><div><CalendarDays size={16} /><strong>Reporting period</strong></div><label>From <input type="date" value={range.start} onChange={(event) => setRange((current) => ({ ...current, start: event.target.value }))} /></label><label>To <input type="date" value={range.end} onChange={(event) => setRange((current) => ({ ...current, end: event.target.value }))} /></label><button className="button button-primary" onClick={load} disabled={loading}>{loading ? <LoaderCircle className="spin" size={15} /> : 'Update report'}</button></div>
    {error && <ErrorState error={error} retry={load} />}
    {report && <><div className="stats-grid report-stats">
      <StatCard label="Measured energy" value={report.measured_kwh.toFixed(3)} unit="kWh" icon={Zap} tone="blue" hint="Integrated measured readings" />
      <StatCard label="Simulated energy" value={report.simulated_kwh.toFixed(3)} unit="kWh" icon={Activity} tone="amber" hint="Integrated demo readings" />
      <StatCard label="Potentially avoidable" value={report.estimated_avoidable_kwh.toFixed(3)} unit="kWh" icon={Lightbulb} tone="green" hint="Confirmed empty-room incidents" />
      <StatCard label="Potential cost savings" value={`₹${report.potential_savings_inr.toFixed(2)}`} icon={GraduationCap} tone="green" hint={`At ₹${report.tariff_inr_per_kwh}/kWh tariff`} />
    </div>
    <div className="dashboard-grid reports-grid">
      <section className="panel report-chart-panel"><div className="panel-heading"><div><h2>Classroom energy comparison</h2><p>Integrated energy from available readings</p></div><span className="demo-tag">kWh</span></div><div className="report-chart">{chart.length ? <Suspense fallback={<Loading />}><ClassroomEnergyChart data={chart} /></Suspense> : <EmptyState title="Not enough readings for a comparison" detail="Generate more readings over time to populate the report." />}</div></section>
      <section className="panel report-breakdown"><div className="panel-heading"><div><h2>Energy breakdown</h2><p>Selected period totals</p></div></div><div className="breakdown-line"><span><i className="breakdown-dot measured" />Measured</span><strong>{report.measured_kwh.toFixed(3)} kWh</strong></div><div className="breakdown-line"><span><i className="breakdown-dot simulated" />Simulated</span><strong>{report.simulated_kwh.toFixed(3)} kWh</strong></div><div className="breakdown-line"><span><i className="breakdown-dot avoidable" />Potentially avoidable</span><strong>{report.estimated_avoidable_kwh.toFixed(3)} kWh</strong></div><div className="report-caveat"><CircleHelp size={15} /><span>Estimates are not actual or verified savings. Gaps between readings are excluded conservatively.</span></div></section>
    </div>
    <section className="panel incidents-panel"><div className="panel-heading"><div><h2>Energy waste incidents</h2><p>Historical and ongoing confirmed empty-room events</p></div><span className="record-count">{report.incidents.length} <small>incidents</small></span></div><div className="records-table-wrap"><table className="data-table"><thead><tr><th>CLASSROOM</th><th>STARTED</th><th>ENDED</th><th>EST. ENERGY</th><th>STATUS</th></tr></thead><tbody>{report.incidents.map((incident) => <tr key={incident.id}><td><strong>{incident.classroom}</strong></td><td>{dateTime(incident.started_at)}</td><td>{dateTime(incident.ended_at)}</td><td>{incident.estimated_kwh.toFixed(4)} kWh</td><td><StatusBadge tone={incident.status === 'active' ? 'warning' : 'green'}>{incident.status}</StatusBadge></td></tr>)}</tbody></table>{!report.incidents.length && <EmptyState title="No incidents in this date range" detail="Only confirmed empty-room incidents are included." />}</div></section>
    <section className="panel incidents-panel"><div className="panel-heading"><div><h2>Historical alert activity</h2><p>Facilities notifications raised during this reporting period</p></div><span className="record-count">{report.alerts.length} <small>alerts</small></span></div><div className="records-table-wrap"><table className="data-table"><thead><tr><th>CLASSROOM</th><th>ALERT</th><th>DETECTED</th><th>POWER</th><th>STATUS</th></tr></thead><tbody>{report.alerts.map((alert) => <tr key={alert.id}><td><strong>{alert.classroom}</strong></td><td>{alert.type}</td><td>{dateTime(alert.created_at)}</td><td>{power(alert.detected_power_watts)}</td><td><StatusBadge tone={alert.status === 'resolved' ? 'green' : alert.severity === 'high' ? 'danger' : 'warning'}>{alert.status}</StatusBadge></td></tr>)}</tbody></table>{!report.alerts.length && <EmptyState title="No alerts in this date range" detail="Any facilities alerts will be listed here." />}</div></section>
    </>}
  </>
}

export default function App() {
  return <BrowserRouter><AppShell /></BrowserRouter>
}
