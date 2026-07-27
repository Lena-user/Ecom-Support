import { useState, useEffect } from 'react'
import { Inbox, CheckCircle, Clock, LogOut, Activity, RefreshCw } from 'lucide-react'
import { useAuth } from '../AuthContext'
import { useNavigate } from 'react-router-dom'

interface Ticket {
  id: string;
  status: 'escalated' | 'resolved' | 'duplicate' | 'processing';
  priority: 'high' | 'low' | '';
  type: string;
  customer: string;
  createdAt: string;
  log: string[];
  similarityScore?: number;
  message?: string;
}

export default function Dashboard() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [selected, setSelected] = useState<Ticket | null>(null)
  const [loading, setLoading] = useState(true)
  const [replyText, setReplyText] = useState('')
  const { logout } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    setReplyText('')
  }, [selected?.id])

  const fetchTickets = async () => {
    setLoading(true)
    try {
      const res = await fetch('http://localhost:8000/api/support/tickets')
      const data = await res.json()
      setTickets(data)
      if (data.length > 0) {
        setSelected(prev => prev ? prev : data[0])
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchTickets()
    // Poll every 5s
    const interval = setInterval(fetchTickets, 5000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div style={{ display: 'flex', height: '100vh', backgroundColor: '#f4f7fb' }}>
      {/* Sidebar */}
      <aside style={{ width: '240px', background: '#fff', borderRight: '1px solid #e0e0e0', padding: '24px 16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <h2 style={{ fontSize: '1.2rem', fontWeight: 600, color: '#0b57d0', marginBottom: '24px', paddingLeft: '8px' }}>Staff Workspace</h2>
        
        <button style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px', borderRadius: '8px', background: '#e8f0fe', color: '#0b57d0', border: 'none', cursor: 'pointer', fontWeight: 500, textAlign: 'left' }}>
          <Inbox size={18} /> Tất cả yêu cầu
        </button>
        <button style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px', borderRadius: '8px', background: 'transparent', color: '#444746', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
          <Clock size={18} /> Cần xử lý
        </button>
        <button style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px', borderRadius: '8px', background: 'transparent', color: '#444746', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
          <CheckCircle size={18} /> Đã xử lý
        </button>
        
        <div style={{ flex: 1 }} />
        <button 
          onClick={() => { logout(); navigate('/login'); }}
          style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px', background: 'transparent', border: 'none', cursor: 'pointer', color: '#c5221f', textAlign: 'left', fontSize: '0.9rem', fontWeight: 500 }}
        >
          <LogOut size={18} /> Đăng xuất
        </button>
      </aside>

      {/* Main List */}
      <main style={{ flex: 1, padding: '24px', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
          <h1 style={{ fontSize: '1.5rem', color: '#1e1e1e' }}>Tất cả yêu cầu</h1>
          <button onClick={fetchTickets} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 16px', background: '#fff', border: '1px solid #e0e0e0', borderRadius: '8px', cursor: 'pointer' }}>
            <RefreshCw size={16} className={loading ? "spin" : ""} /> Làm mới
          </button>
        </div>
        
        <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e0e0e0', overflow: 'hidden', flex: 1, display: 'flex', flexDirection: 'column' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead style={{ background: '#f8f9fa', borderBottom: '1px solid #e0e0e0' }}>
              <tr>
                <th style={{ padding: '16px', fontWeight: 500, color: '#444746' }}>Ticket ID</th>
                <th style={{ padding: '16px', fontWeight: 500, color: '#444746' }}>Khách hàng</th>
                <th style={{ padding: '16px', fontWeight: 500, color: '#444746' }}>Nội dung</th>
                <th style={{ padding: '16px', fontWeight: 500, color: '#444746' }}>Trạng thái</th>
                <th style={{ padding: '16px', fontWeight: 500, color: '#444746' }}>Thời gian</th>
              </tr>
            </thead>
            <tbody>
              {tickets.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ padding: '32px', textAlign: 'center', color: '#888' }}>
                    Chưa có ticket nào. Hãy qua trang Khách hàng chat vài câu nhé!
                  </td>
                </tr>
              ) : (
                tickets.map(t => (
                  <tr key={t.id} onClick={() => setSelected(t)} style={{ cursor: 'pointer', background: selected?.id === t.id ? '#f4f7fb' : '#fff', borderBottom: '1px solid #eee' }}>
                    <td style={{ padding: '16px', fontWeight: 500 }}>{t.id}</td>
                    <td style={{ padding: '16px' }}>{t.customer}</td>
                    <td style={{ padding: '16px', maxWidth: '200px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.message || t.type}</td>
                    <td style={{ padding: '16px' }}>
                      <span style={{ 
                        padding: '4px 8px', borderRadius: '4px', fontSize: '0.8rem', fontWeight: 600,
                        background: t.status === 'escalated' ? '#fce8e6' : t.status === 'duplicate' ? '#fef7e0' : '#e6f4ea',
                        color: t.status === 'escalated' ? '#c5221f' : t.status === 'duplicate' ? '#b06000' : '#137333'
                      }}>
                        {t.status?.toUpperCase()}
                      </span>
                    </td>
                    <td style={{ padding: '16px', color: '#888' }}>{t.createdAt}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </main>

      {/* Detail Panel */}
      {selected && (
        <aside style={{ width: '380px', background: '#fff', borderLeft: '1px solid #e0e0e0', padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px', overflowY: 'auto' }}>
          <div>
            <h2 style={{ fontSize: '1.2rem', marginBottom: '8px' }}>Chi tiết Ticket: {selected.id}</h2>
            <div style={{ display: 'flex', gap: '8px' }}>
              <span style={{ padding: '4px 8px', borderRadius: '4px', fontSize: '0.8rem', fontWeight: 600, background: '#f0f4f9', color: '#444746' }}>Type: {selected.type || 'unknown'}</span>
              {selected.priority && <span style={{ padding: '4px 8px', borderRadius: '4px', fontSize: '0.8rem', fontWeight: 600, background: '#fce8e6', color: '#c5221f' }}>Priority: {selected.priority}</span>}
              {selected.similarityScore !== undefined && selected.similarityScore > 0 && <span style={{ padding: '4px 8px', borderRadius: '4px', fontSize: '0.8rem', fontWeight: 600, background: '#e6f4ea', color: '#137333' }}>RAG: {(selected.similarityScore * 100).toFixed(1)}%</span>}
            </div>
          </div>
          
          <div style={{ background: '#f8f9fa', padding: '16px', borderRadius: '8px', border: '1px solid #eee' }}>
            <h3 style={{ fontSize: '0.9rem', color: '#888', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}><Activity size={16} /> AI Processing Log</h3>
            {selected.log?.map((l, i) => (
              <div key={i} style={{ fontSize: '0.85rem', color: '#444746', marginBottom: '4px', paddingBottom: '4px', borderBottom: '1px dashed #e0e0e0' }}>{l}</div>
            ))}
          </div>

          <div style={{ flex: 1 }} />
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <textarea 
              placeholder="Nhập phản hồi thủ công cho khách hàng..." 
              value={replyText}
              onChange={e => setReplyText(e.target.value)}
              style={{ padding: '12px', borderRadius: '8px', border: '1px solid #ccc', minHeight: '100px', resize: 'none', fontFamily: 'inherit' }} 
            />
            <button 
              onClick={() => {
                if (!replyText.trim()) return;
                alert(`Đã gửi phản hồi cho khách hàng: ${replyText}`);
                setReplyText('');
              }}
              style={{ padding: '12px', background: '#0b57d0', color: '#fff', border: 'none', borderRadius: '8px', fontWeight: 600, cursor: 'pointer', opacity: replyText.trim() ? 1 : 0.6 }}
              disabled={!replyText.trim()}
            >
              Gửi phản hồi
            </button>
          </div>
        </aside>
      )}
    </div>
  )
}
