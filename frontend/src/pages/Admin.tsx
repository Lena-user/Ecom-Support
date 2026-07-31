import { useState, useEffect, useCallback } from 'react'
import { LayoutDashboard, Settings, Server, Users, LogOut, BookOpen, Pencil, Trash2, UserPlus } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, BarChart, Bar, Legend } from 'recharts'
import { useAuth } from '../AuthContext'
import { useNavigate } from 'react-router-dom'
import { API_BASE } from '../config'

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#82ca9d']

interface Stats {
  total_requests: number
  auto_resolved_rate: number
  escalated_count: number
  by_classification: Record<string, number>
  by_type_status: Record<string, { auto: number; escalate: number }>
  requests_by_hour: [string, number][]
  recent_logs: string[]
  csat_positive: number
  csat_negative: number
  csat_total: number
}

interface Health {
  healthy: boolean
  services: Record<string, string>
}

interface AISettings {
  similarity_threshold: number
  duplicate_window_hours: number
  escalate_keywords: string[]
}

interface KBDoc {
  id: string
  source: string
  content: string
}

interface KnowledgeGap {
  message: string
  reasoning: string
  ticket_id: string
  classification: string
  timestamp: number
}

interface StaffAccount {
  email: string
  name: string
  role: 'staff' | 'admin'
  ticket_count: number
}

export default function Admin() {
  const [activeTab, setActiveTab] = useState('overview')
  const [stats, setStats] = useState<Stats | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const { logout, token, userEmail } = useAuth()
  const navigate = useNavigate()
  const authHeaders = { Authorization: `Bearer ${token}` }

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/support/stats`, { headers: authHeaders })
      if (res.status === 401) {
        logout()
        navigate('/login')
        return
      }
      setStats(await res.json())
    } catch (err) {
      console.error('Fetch stats failed:', err)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/health`)
      setHealth(await res.json())
    } catch (err) {
      console.error('Fetch health failed:', err)
    }
  }, [])

  useEffect(() => {
    fetchStats()
    fetchHealth()
    const interval = setInterval(() => {
      fetchStats()
      fetchHealth()
    }, 5000)
    return () => clearInterval(interval)
  }, [fetchStats, fetchHealth])

  const dataLine = (stats?.requests_by_hour ?? []).map(([time, requests]) => ({ time, requests }))
  const dataPie = Object.entries(stats?.by_classification ?? {}).map(([name, value]) => ({ name, value }))
  const dataBar = Object.entries(stats?.by_type_status ?? {}).map(([name, v]) => ({ name, ...v }))

  // ── Cấu hình AI ──────────────────────────────────────────────────────
  const [aiSettings, setAiSettings] = useState<AISettings | null>(null)
  const [keywordsText, setKeywordsText] = useState('')
  const [savingSettings, setSavingSettings] = useState(false)
  const [settingsSaved, setSettingsSaved] = useState(false)

  useEffect(() => {
    if (activeTab !== 'config') return
    fetch(`${API_BASE}/api/support/settings`, { headers: authHeaders })
      .then(res => res.json())
      .then((data: AISettings) => {
        setAiSettings(data)
        setKeywordsText(data.escalate_keywords.join(', '))
      })
      .catch(err => console.error('Fetch settings failed:', err))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, token])

  const handleSaveSettings = async () => {
    if (!aiSettings) return
    setSavingSettings(true)
    setSettingsSaved(false)
    try {
      const payload = {
        ...aiSettings,
        escalate_keywords: keywordsText.split(',').map(k => k.trim()).filter(Boolean),
      }
      const res = await fetch(`${API_BASE}/api/support/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify(payload),
      })
      const saved: AISettings = await res.json()
      setAiSettings(saved)
      setKeywordsText(saved.escalate_keywords.join(', '))
      setSettingsSaved(true)
    } catch (err) {
      console.error('Save settings failed:', err)
    } finally {
      setSavingSettings(false)
    }
  }

  // ── Knowledge Base ───────────────────────────────────────────────────
  const [kbDocs, setKbDocs] = useState<KBDoc[]>([])
  const [kbEditingId, setKbEditingId] = useState<string | null>(null)
  const [kbSource, setKbSource] = useState('')
  const [kbContent, setKbContent] = useState('')

  const fetchKbDocs = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/support/kb`, { headers: authHeaders })
      setKbDocs(await res.json())
    } catch (err) {
      console.error('Fetch KB failed:', err)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  useEffect(() => {
    if (activeTab === 'kb') fetchKbDocs()
  }, [activeTab, fetchKbDocs])

  const resetKbForm = () => {
    setKbEditingId(null)
    setKbSource('')
    setKbContent('')
  }

  // ── Khoảng trống kiến thức (câu hỏi AI chưa đủ căn cứ trả lời) ────────
  const [knowledgeGaps, setKnowledgeGaps] = useState<KnowledgeGap[]>([])

  const fetchKnowledgeGaps = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/support/knowledge-gaps`, { headers: authHeaders })
      setKnowledgeGaps(await res.json())
    } catch (err) {
      console.error('Fetch knowledge gaps failed:', err)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  useEffect(() => {
    if (activeTab === 'kb') fetchKnowledgeGaps()
  }, [activeTab, fetchKnowledgeGaps])

  const handleUseGapAsNewDoc = (gap: KnowledgeGap) => {
    setKbEditingId(null)
    setKbSource(gap.message.length > 60 ? `${gap.message.slice(0, 60)}...` : gap.message)
    setKbContent('')
  }

  const handleSubmitKbDoc = async () => {
    if (!kbSource.trim() || !kbContent.trim()) return
    const url = kbEditingId ? `${API_BASE}/api/support/kb/${kbEditingId}` : `${API_BASE}/api/support/kb`
    const method = kbEditingId ? 'PUT' : 'POST'
    try {
      await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({ source: kbSource.trim(), content: kbContent.trim() }),
      })
      resetKbForm()
      fetchKbDocs()
    } catch (err) {
      console.error('Save KB doc failed:', err)
    }
  }

  const handleEditKbDoc = (doc: KBDoc) => {
    setKbEditingId(doc.id)
    setKbSource(doc.source)
    setKbContent(doc.content)
  }

  const handleDeleteKbDoc = async (id: string) => {
    try {
      await fetch(`${API_BASE}/api/support/kb/${id}`, { method: 'DELETE', headers: authHeaders })
      if (kbEditingId === id) resetKbForm()
      fetchKbDocs()
    } catch (err) {
      console.error('Delete KB doc failed:', err)
    }
  }

  // ── Quản lý nhân sự ───────────────────────────────────────────────────
  const [staffList, setStaffList] = useState<StaffAccount[]>([])
  const [staffEmail, setStaffEmail] = useState('')
  const [staffName, setStaffName] = useState('')
  const [staffPassword, setStaffPassword] = useState('')
  const [staffRole, setStaffRole] = useState<'staff' | 'admin'>('staff')
  const [staffError, setStaffError] = useState('')

  const fetchStaff = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/support/staff`, { headers: authHeaders })
      setStaffList(await res.json())
    } catch (err) {
      console.error('Fetch staff failed:', err)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  useEffect(() => {
    if (activeTab === 'staff') fetchStaff()
  }, [activeTab, fetchStaff])

  const resetStaffForm = () => {
    setStaffEmail('')
    setStaffName('')
    setStaffPassword('')
    setStaffRole('staff')
    setStaffError('')
  }

  const handleCreateStaff = async () => {
    if (!staffEmail.trim() || !staffName.trim() || staffPassword.length < 3) {
      setStaffError('Vui lòng nhập đủ email, tên, mật khẩu (tối thiểu 3 ký tự).')
      return
    }
    setStaffError('')
    try {
      const res = await fetch(`${API_BASE}/api/support/staff`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({ email: staffEmail.trim(), name: staffName.trim(), password: staffPassword, role: staffRole }),
      })
      if (res.status === 409) {
        setStaffError('Email này đã tồn tại.')
        return
      }
      resetStaffForm()
      fetchStaff()
    } catch (err) {
      console.error('Create staff failed:', err)
    }
  }

  const handleDeleteStaff = async (email: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/support/staff/${encodeURIComponent(email)}`, {
        method: 'DELETE',
        headers: authHeaders,
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        alert(data.detail || 'Không thể xoá tài khoản này.')
        return
      }
      fetchStaff()
    } catch (err) {
      console.error('Delete staff failed:', err)
    }
  }

  return (
    <div style={{ display: 'flex', height: '100vh', backgroundColor: '#f4f7fb' }}>
      {/* Admin Sidebar */}
      <aside style={{ width: '260px', background: '#1e1e1e', color: '#fff', padding: '24px 16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <h2 style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '24px', paddingLeft: '8px' }}>System Admin</h2>
        
        <button onClick={() => setActiveTab('overview')} style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px', borderRadius: '8px', background: activeTab === 'overview' ? '#333' : 'transparent', color: '#fff', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
          <LayoutDashboard size={18} /> Tổng quan
        </button>
        <button onClick={() => setActiveTab('config')} style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px', borderRadius: '8px', background: activeTab === 'config' ? '#333' : 'transparent', color: '#fff', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
          <Settings size={18} /> Cấu hình AI
        </button>
        <button onClick={() => setActiveTab('kb')} style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px', borderRadius: '8px', background: activeTab === 'kb' ? '#333' : 'transparent', color: '#fff', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
          <BookOpen size={18} /> Knowledge Base
        </button>
        <button onClick={() => setActiveTab('monitor')} style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px', borderRadius: '8px', background: activeTab === 'monitor' ? '#333' : 'transparent', color: '#fff', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
          <Server size={18} /> Giám sát vận hành
        </button>
        <button onClick={() => setActiveTab('staff')} style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px', borderRadius: '8px', background: activeTab === 'staff' ? '#333' : 'transparent', color: '#fff', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
          <Users size={18} /> Quản lý nhân sự
        </button>
        
        <div style={{ flex: 1 }} />
        <button 
          onClick={() => { logout(); navigate('/login'); }}
          style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px', background: 'transparent', border: 'none', cursor: 'pointer', color: '#ff6b6b', textAlign: 'left', fontSize: '0.9rem' }}
        >
          <LogOut size={18} /> Đăng xuất
        </button>
      </aside>

      {/* Main Content */}
      <main style={{ flex: 1, padding: '32px', overflowY: 'auto' }}>
        {activeTab === 'overview' && (
          <div>
            <h1 style={{ fontSize: '1.5rem', marginBottom: '24px', color: '#1e1e1e' }}>Tổng quan hệ thống</h1>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '24px', marginBottom: '32px' }}>
              <div style={{ background: '#fff', padding: '24px', borderRadius: '12px', boxShadow: '0 2px 4px rgba(0,0,0,0.02)' }}>
                <div style={{ color: '#888', fontSize: '0.9rem' }}>Tổng requests</div>
                <div style={{ fontSize: '2rem', fontWeight: 600, color: '#0b57d0' }}>{stats?.total_requests ?? 0}</div>
              </div>
              <div style={{ background: '#fff', padding: '24px', borderRadius: '12px', boxShadow: '0 2px 4px rgba(0,0,0,0.02)' }}>
                <div style={{ color: '#888', fontSize: '0.9rem' }}>Tỷ lệ tự động xử lý (AI)</div>
                <div style={{ fontSize: '2rem', fontWeight: 600, color: '#137333' }}>{stats?.auto_resolved_rate ?? 0}%</div>
              </div>
              <div style={{ background: '#fff', padding: '24px', borderRadius: '12px', boxShadow: '0 2px 4px rgba(0,0,0,0.02)' }}>
                <div style={{ color: '#888', fontSize: '0.9rem' }}>Số ca chuyển nhân viên</div>
                <div style={{ fontSize: '2rem', fontWeight: 600, color: '#c5221f' }}>{stats?.escalated_count ?? 0}</div>
              </div>
              <div style={{ background: '#fff', padding: '24px', borderRadius: '12px', boxShadow: '0 2px 4px rgba(0,0,0,0.02)' }}>
                <div style={{ color: '#888', fontSize: '0.9rem' }}>Tỷ lệ hài lòng (CSAT)</div>
                <div style={{ fontSize: '2rem', fontWeight: 600, color: '#0b57d0' }}>
                  {stats && stats.csat_total > 0 ? `${Math.round((stats.csat_positive / stats.csat_total) * 100)}%` : '—'}
                </div>
                <div style={{ fontSize: '0.78rem', color: '#9aa0a6', marginTop: '2px' }}>
                  {stats?.csat_total ? `${stats.csat_positive}/${stats.csat_total} lượt đánh giá` : 'Chưa có đánh giá'}
                </div>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
              <div style={{ background: '#fff', padding: '24px', borderRadius: '12px', height: '350px' }}>
                <h3 style={{ marginBottom: '16px' }}>Request theo thời gian</h3>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={dataLine}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="time" />
                    <YAxis />
                    <Tooltip />
                    <Line type="monotone" dataKey="requests" stroke="#0b57d0" strokeWidth={3} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              <div style={{ background: '#fff', padding: '24px', borderRadius: '12px', height: '350px' }}>
                <h3 style={{ marginBottom: '16px' }}>Phân bố loại yêu cầu</h3>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={dataPie} cx="50%" cy="50%" innerRadius={60} outerRadius={100} fill="#8884d8" paddingAngle={5} dataKey="value">
                      {dataPie.map((_entry, index) => <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />)}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              <div style={{ background: '#fff', padding: '24px', borderRadius: '12px', height: '350px', gridColumn: 'span 2' }}>
                <h3 style={{ marginBottom: '16px' }}>Tỷ lệ xử lý Tự động vs Chuyển nhân viên</h3>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={dataBar}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="auto" stackId="a" fill="#137333" name="Auto-Resolved (AI)" />
                    <Bar dataKey="escalate" stackId="a" fill="#c5221f" name="Escalated (Human)" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'config' && (
          <div>
            <h1 style={{ fontSize: '1.5rem', marginBottom: '24px', color: '#1e1e1e' }}>Cấu hình AI Routing</h1>
            {!aiSettings ? (
              <p style={{ color: '#888' }}>Đang tải cấu hình...</p>
            ) : (
              <div style={{ background: '#fff', padding: '24px', borderRadius: '12px', display: 'flex', flexDirection: 'column', gap: '24px', maxWidth: '600px' }}>
                <div>
                  <label style={{ display: 'block', fontWeight: 500, marginBottom: '8px' }}>
                    RAG Similarity Threshold ({aiSettings.similarity_threshold.toFixed(2)})
                  </label>
                  <input
                    type="range" min="0" max="1" step="0.05"
                    value={aiSettings.similarity_threshold}
                    onChange={e => setAiSettings({ ...aiSettings, similarity_threshold: parseFloat(e.target.value) })}
                    style={{ width: '100%' }}
                  />
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: '#888' }}>
                    <span>Loose (0.5)</span>
                    <span>Strict (0.9)</span>
                  </div>
                </div>

                <div>
                  <label style={{ display: 'block', fontWeight: 500, marginBottom: '8px' }}>Duplicate Time Window (hours)</label>
                  <input
                    type="number" min={1}
                    value={aiSettings.duplicate_window_hours}
                    onChange={e => setAiSettings({ ...aiSettings, duplicate_window_hours: parseInt(e.target.value, 10) || 1 })}
                    style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #ccc' }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontWeight: 500, marginBottom: '8px' }}>Từ khóa Escalate thủ công (Cách nhau bằng dấu phẩy)</label>
                  <textarea
                    value={keywordsText}
                    onChange={e => setKeywordsText(e.target.value)}
                    style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #ccc', minHeight: '80px', resize: 'none' }}
                  />
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                  <button
                    onClick={handleSaveSettings}
                    disabled={savingSettings}
                    style={{ padding: '12px 24px', background: '#0b57d0', color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 600, cursor: 'pointer' }}
                  >
                    {savingSettings ? 'Đang lưu...' : 'Lưu cấu hình'}
                  </button>
                  {settingsSaved && <span style={{ color: '#137333', fontWeight: 500 }}>Đã lưu.</span>}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'kb' && (
          <div>
            <h1 style={{ fontSize: '1.5rem', marginBottom: '24px', color: '#1e1e1e' }}>Knowledge Base (RAG)</h1>

            <div style={{ background: '#fff3cd', padding: '20px 24px', borderRadius: '12px', maxWidth: '700px', marginBottom: '24px' }}>
              <h3 style={{ margin: '0 0 4px 0', color: '#856404' }}>Câu hỏi bot chưa trả lời được</h3>
              <p style={{ margin: '0 0 12px 0', fontSize: '0.85rem', color: '#a07800' }}>
                AI đánh giá không đủ căn cứ tài liệu để trả lời — đã chuyển nhân viên. Bấm vào 1 mục để thêm tài liệu bổ sung.
              </p>
              {knowledgeGaps.length === 0 ? (
                <p style={{ fontSize: '0.85rem', color: '#a07800', margin: 0 }}>Chưa có khoảng trống nào được ghi nhận.</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {knowledgeGaps.map((gap, i) => (
                    <button
                      key={i}
                      onClick={() => handleUseGapAsNewDoc(gap)}
                      style={{
                        textAlign: 'left', background: '#fff', border: '1px solid #f0d78c', borderRadius: '8px',
                        padding: '10px 14px', cursor: 'pointer', fontSize: '0.85rem', color: '#664d03',
                      }}
                    >
                      <div style={{ fontWeight: 600 }}>{gap.message}</div>
                      <div style={{ color: '#a07800', marginTop: '2px' }}>{gap.reasoning}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div style={{ background: '#fff', padding: '24px', borderRadius: '12px', display: 'flex', flexDirection: 'column', gap: '16px', maxWidth: '700px', marginBottom: '24px' }}>
              <h3 style={{ margin: 0 }}>{kbEditingId ? 'Sửa tài liệu' : 'Thêm tài liệu mới'}</h3>
              <div>
                <label style={{ display: 'block', fontWeight: 500, marginBottom: '8px' }}>Nguồn</label>
                <input
                  value={kbSource}
                  onChange={e => setKbSource(e.target.value)}
                  placeholder="VD: Chính sách đổi trả"
                  style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #ccc' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontWeight: 500, marginBottom: '8px' }}>Nội dung</label>
                <textarea
                  value={kbContent}
                  onChange={e => setKbContent(e.target.value)}
                  style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #ccc', minHeight: '100px', resize: 'vertical' }}
                />
              </div>
              <div style={{ display: 'flex', gap: '12px' }}>
                <button
                  onClick={handleSubmitKbDoc}
                  style={{ padding: '10px 20px', background: '#0b57d0', color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 600, cursor: 'pointer' }}
                >
                  {kbEditingId ? 'Cập nhật' : 'Thêm tài liệu'}
                </button>
                {kbEditingId && (
                  <button
                    onClick={resetKbForm}
                    style={{ padding: '10px 20px', background: '#f1f3f4', color: '#5f6368', border: 'none', borderRadius: '6px', fontWeight: 600, cursor: 'pointer' }}
                  >
                    Huỷ
                  </button>
                )}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {kbDocs.length === 0 ? (
                <p style={{ color: '#888' }}>Chưa có tài liệu nào.</p>
              ) : (
                kbDocs.map(doc => (
                  <div key={doc.id} style={{ background: '#fff', padding: '16px 20px', borderRadius: '12px', display: 'flex', justifyContent: 'space-between', gap: '16px', maxWidth: '700px' }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 600, marginBottom: '4px' }}>{doc.source}</div>
                      <div style={{ color: '#5f6368', fontSize: '0.9rem', overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                        {doc.content}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
                      <button onClick={() => handleEditKbDoc(doc)} style={{ padding: '8px', background: '#f1f3f4', border: 'none', borderRadius: '6px', cursor: 'pointer', color: '#5f6368' }}>
                        <Pencil size={16} />
                      </button>
                      <button onClick={() => handleDeleteKbDoc(doc.id)} style={{ padding: '8px', background: '#fce8e6', border: 'none', borderRadius: '6px', cursor: 'pointer', color: '#c5221f' }}>
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {activeTab === 'monitor' && (
          <div>
            <h1 style={{ fontSize: '1.5rem', marginBottom: '24px', color: '#1e1e1e' }}>Giám sát vận hành</h1>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '24px' }}>
              {['redis', 'qdrant'].map(service => {
                const status = health?.services?.[service]
                const ok = status === 'ok'
                return (
                  <div key={service} style={{ background: '#fff', padding: '24px', borderRadius: '12px', borderLeft: `4px solid ${ok ? '#137333' : '#c5221f'}` }}>
                    <h3 style={{ fontSize: '1rem', color: '#444' }}>{service === 'redis' ? 'Redis Store' : 'Qdrant Vector DB'}</h3>
                    <p style={{ color: ok ? '#137333' : '#c5221f', fontWeight: 600, fontSize: '1.2rem', marginTop: '8px' }}>
                      {status ? (ok ? 'Online' : status) : 'Đang kiểm tra...'}
                    </p>
                  </div>
                )
              })}
            </div>

            <h3 style={{ marginTop: '32px', marginBottom: '16px' }}>System Logs (từ processing_log các session gần đây)</h3>
            <div style={{ background: '#1e1e1e', color: '#4af626', padding: '16px', borderRadius: '8px', fontFamily: 'monospace', height: '300px', overflowY: 'auto', fontSize: '0.9rem' }}>
              {(stats?.recent_logs?.length ?? 0) === 0
                ? <div style={{ color: '#888' }}>Chưa có log nào.</div>
                : stats!.recent_logs.map((line, i) => <div key={i}>{line}</div>)
              }
            </div>
          </div>
        )}

        {activeTab === 'staff' && (
          <div>
            <h1 style={{ fontSize: '1.5rem', marginBottom: '24px', color: '#1e1e1e' }}>Quản lý Nhân sự CSKH</h1>

            <div style={{ background: '#fff', padding: '24px', borderRadius: '12px', display: 'flex', flexDirection: 'column', gap: '16px', maxWidth: '600px', marginBottom: '24px' }}>
              <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}><UserPlus size={18} /> Thêm tài khoản mới</h3>
              {staffError && <div style={{ color: '#c5221f', background: '#fce8e6', padding: '10px 14px', borderRadius: '8px', fontSize: '0.85rem' }}>{staffError}</div>}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <input
                  value={staffEmail}
                  onChange={e => setStaffEmail(e.target.value)}
                  placeholder="Email"
                  style={{ padding: '10px', borderRadius: '6px', border: '1px solid #ccc' }}
                />
                <input
                  value={staffName}
                  onChange={e => setStaffName(e.target.value)}
                  placeholder="Tên hiển thị"
                  style={{ padding: '10px', borderRadius: '6px', border: '1px solid #ccc' }}
                />
                <input
                  type="password"
                  value={staffPassword}
                  onChange={e => setStaffPassword(e.target.value)}
                  placeholder="Mật khẩu"
                  style={{ padding: '10px', borderRadius: '6px', border: '1px solid #ccc' }}
                />
                <select
                  value={staffRole}
                  onChange={e => setStaffRole(e.target.value as 'staff' | 'admin')}
                  style={{ padding: '10px', borderRadius: '6px', border: '1px solid #ccc' }}
                >
                  <option value="staff">Nhân viên</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <button
                onClick={handleCreateStaff}
                style={{ padding: '10px 20px', background: '#0b57d0', color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 600, cursor: 'pointer', alignSelf: 'flex-start' }}
              >
                Thêm tài khoản
              </button>
            </div>

            <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e0e0e0', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                <thead style={{ background: '#f8f9fa', borderBottom: '1px solid #e0e0e0' }}>
                  <tr>
                    <th style={{ padding: '16px', fontWeight: 500, color: '#444746' }}>Nhân viên</th>
                    <th style={{ padding: '16px', fontWeight: 500, color: '#444746' }}>Email</th>
                    <th style={{ padding: '16px', fontWeight: 500, color: '#444746' }}>Vai trò</th>
                    <th style={{ padding: '16px', fontWeight: 500, color: '#444746' }}>Tickets xử lý</th>
                    <th style={{ padding: '16px', fontWeight: 500, color: '#444746' }}></th>
                  </tr>
                </thead>
                <tbody>
                  {staffList.length === 0 ? (
                    <tr><td colSpan={5} style={{ padding: '24px', textAlign: 'center', color: '#888' }}>Chưa có tài khoản nào.</td></tr>
                  ) : (
                    staffList.map(s => (
                      <tr key={s.email} style={{ borderBottom: '1px solid #eee' }}>
                        <td style={{ padding: '16px', fontWeight: 500 }}>{s.name}</td>
                        <td style={{ padding: '16px', color: '#888' }}>{s.email}</td>
                        <td style={{ padding: '16px' }}>{s.role === 'admin' ? 'Admin' : 'Nhân viên'}</td>
                        <td style={{ padding: '16px' }}>{s.ticket_count}</td>
                        <td style={{ padding: '16px', textAlign: 'right' }}>
                          {s.email !== userEmail && (
                            <button
                              onClick={() => handleDeleteStaff(s.email)}
                              style={{ padding: '6px', background: '#fce8e6', border: 'none', borderRadius: '6px', cursor: 'pointer', color: '#c5221f' }}
                            >
                              <Trash2 size={14} />
                            </button>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
