import { useState } from 'react'
import { LayoutDashboard, Settings, Server, Users, LogOut } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, BarChart, Bar, Legend } from 'recharts'
import { useAuth } from '../AuthContext'
import { useNavigate } from 'react-router-dom'

const dataLine = [
  { time: '08:00', requests: 10 },
  { time: '10:00', requests: 45 },
  { time: '12:00', requests: 30 },
  { time: '14:00', requests: 60 },
  { time: '16:00', requests: 80 },
  { time: '18:00', requests: 40 },
]

const dataPie = [
  { name: 'Info', value: 400 },
  { name: 'Complaint', value: 300 },
  { name: 'Refund', value: 300 },
  { name: 'Other', value: 200 },
]

const dataBar = [
  { name: 'Info', auto: 80, escalate: 20 },
  { name: 'Complaint', auto: 30, escalate: 70 },
  { name: 'Refund', auto: 50, escalate: 50 },
]

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042']

export default function Admin() {
  const [activeTab, setActiveTab] = useState('overview')
  const { logout } = useAuth()
  const navigate = useNavigate()

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
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '24px', marginBottom: '32px' }}>
              <div style={{ background: '#fff', padding: '24px', borderRadius: '12px', boxShadow: '0 2px 4px rgba(0,0,0,0.02)' }}>
                <div style={{ color: '#888', fontSize: '0.9rem' }}>Tổng requests (Hôm nay)</div>
                <div style={{ fontSize: '2rem', fontWeight: 600, color: '#0b57d0' }}>1,245</div>
              </div>
              <div style={{ background: '#fff', padding: '24px', borderRadius: '12px', boxShadow: '0 2px 4px rgba(0,0,0,0.02)' }}>
                <div style={{ color: '#888', fontSize: '0.9rem' }}>Tỷ lệ tự động xử lý (AI)</div>
                <div style={{ fontSize: '2rem', fontWeight: 600, color: '#137333' }}>72.5%</div>
              </div>
              <div style={{ background: '#fff', padding: '24px', borderRadius: '12px', boxShadow: '0 2px 4px rgba(0,0,0,0.02)' }}>
                <div style={{ color: '#888', fontSize: '0.9rem' }}>Tiết kiệm chi phí</div>
                <div style={{ fontSize: '2rem', fontWeight: 600, color: '#c5221f' }}>$450</div>
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
            <div style={{ background: '#fff', padding: '24px', borderRadius: '12px', display: 'flex', flexDirection: 'column', gap: '24px', maxWidth: '600px' }}>
              <div>
                <label style={{ display: 'block', fontWeight: 500, marginBottom: '8px' }}>RAG Similarity Threshold</label>
                <input type="range" min="0" max="1" step="0.05" defaultValue="0.75" style={{ width: '100%' }} />
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: '#888' }}>
                  <span>Loose (0.5)</span>
                  <span>Strict (0.9)</span>
                </div>
              </div>
              
              <div>
                <label style={{ display: 'block', fontWeight: 500, marginBottom: '8px' }}>Duplicate Time Window (hours)</label>
                <input type="number" defaultValue="24" style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #ccc' }} />
              </div>
              
              <div>
                <label style={{ display: 'block', fontWeight: 500, marginBottom: '8px' }}>Từ khóa Escalate thủ công (Cách nhau bằng dấu phẩy)</label>
                <textarea defaultValue="kiện, pháp luật, báo chí, lừa đảo" style={{ width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #ccc', minHeight: '80px', resize: 'none' }} />
              </div>
              
              <button style={{ padding: '12px', background: '#0b57d0', color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 600, cursor: 'pointer' }}>Lưu cấu hình</button>
            </div>
          </div>
        )}

        {activeTab === 'monitor' && (
          <div>
            <h1 style={{ fontSize: '1.5rem', marginBottom: '24px', color: '#1e1e1e' }}>Giám sát vận hành</h1>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '24px' }}>
              <div style={{ background: '#fff', padding: '24px', borderRadius: '12px', borderLeft: '4px solid #137333' }}>
                <h3 style={{ fontSize: '1rem', color: '#444' }}>Redis Store</h3>
                <p style={{ color: '#137333', fontWeight: 600, fontSize: '1.2rem', marginTop: '8px' }}>Online (3ms ping)</p>
              </div>
              <div style={{ background: '#fff', padding: '24px', borderRadius: '12px', borderLeft: '4px solid #137333' }}>
                <h3 style={{ fontSize: '1rem', color: '#444' }}>Qdrant Vector DB</h3>
                <p style={{ color: '#137333', fontWeight: 600, fontSize: '1.2rem', marginTop: '8px' }}>Online (15ms ping)</p>
              </div>
              <div style={{ background: '#fff', padding: '24px', borderRadius: '12px', borderLeft: '4px solid #f9ab00' }}>
                <h3 style={{ fontSize: '1rem', color: '#444' }}>Gemini API Limit</h3>
                <p style={{ color: '#f9ab00', fontWeight: 600, fontSize: '1.2rem', marginTop: '8px' }}>Warning: 45/50 RPM</p>
              </div>
            </div>
            
            <h3 style={{ marginTop: '32px', marginBottom: '16px' }}>System Logs</h3>
            <div style={{ background: '#1e1e1e', color: '#4af626', padding: '16px', borderRadius: '8px', fontFamily: 'monospace', height: '300px', overflowY: 'auto', fontSize: '0.9rem' }}>
              <div>[2026-07-26 14:00:01] INFO: App startup complete</div>
              <div>[2026-07-26 14:05:12] WARNING: Qdrant search took 400ms (threshold 200ms)</div>
              <div>[2026-07-26 14:10:05] ERROR: Gemini Rate Limit Exceeded - retrying...</div>
              <div>[2026-07-26 14:10:07] INFO: Gemini request successful on retry</div>
            </div>
          </div>
        )}

        {activeTab === 'staff' && (
          <div>
            <h1 style={{ fontSize: '1.5rem', marginBottom: '24px', color: '#1e1e1e' }}>Quản lý Nhân sự CSKH</h1>
            <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e0e0e0', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                <thead style={{ background: '#f8f9fa', borderBottom: '1px solid #e0e0e0' }}>
                  <tr>
                    <th style={{ padding: '16px', fontWeight: 500, color: '#444746' }}>Nhân viên</th>
                    <th style={{ padding: '16px', fontWeight: 500, color: '#444746' }}>Email</th>
                    <th style={{ padding: '16px', fontWeight: 500, color: '#444746' }}>Tickets xử lý</th>
                    <th style={{ padding: '16px', fontWeight: 500, color: '#444746' }}>Thời gian trung bình (phút)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr style={{ borderBottom: '1px solid #eee' }}>
                    <td style={{ padding: '16px', fontWeight: 500 }}>Nguyễn Văn A</td>
                    <td style={{ padding: '16px', color: '#888' }}>nva@company.com</td>
                    <td style={{ padding: '16px' }}>420</td>
                    <td style={{ padding: '16px', color: '#137333', fontWeight: 600 }}>4.5</td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid #eee' }}>
                    <td style={{ padding: '16px', fontWeight: 500 }}>Trần Thị B</td>
                    <td style={{ padding: '16px', color: '#888' }}>ttb@company.com</td>
                    <td style={{ padding: '16px' }}>385</td>
                    <td style={{ padding: '16px', color: '#f9ab00', fontWeight: 600 }}>8.2</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
