import { useState, useEffect, useRef, useCallback } from 'react'
import { Inbox, CheckCircle, Clock, LogOut, Activity, UserCheck, XCircle, Send, User, Headset, MessageCircle, Search } from 'lucide-react'
import { useAuth } from '../AuthContext'
import { useNavigate } from 'react-router-dom'
import { API_BASE, WS_BASE } from '../config'

interface Ticket {
  id: string;
  status: 'AI_HANDLING' | 'PENDING_ESCALATION' | 'HUMAN_HANDLING' | 'RESOLVED';
  priority: 'high' | 'low' | '';
  type: string;
  customer: string;
  createdAt: string;
  log: string[];
  message?: string;
  staff_assigned?: string | null;
  escalation_reason?: string;
}

type FilterTab = 'ALL' | 'PENDING' | 'HANDLING' | 'RESOLVED'

export default function Dashboard() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [selected, setSelected] = useState<Ticket | null>(null)
  const [filterTab, setFilterTab] = useState<FilterTab>('ALL')
  const [loading, setLoading] = useState(true)
  const [replyText, setReplyText] = useState('')
  const [liveMessages, setLiveMessages] = useState<{role: string, content: string}[]>([])
  const [showLog, setShowLog] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const wsTicketIdRef = useRef<string | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)
  const { logout, userName, token } = useAuth()
  const navigate = useNavigate()
  const authHeaders = { Authorization: `Bearer ${token}` }

  // ── WebSocket ──────────────────────────────────────────────────────
  useEffect(() => {
    const ticketId = selected?.id ?? null
    const isLive = selected?.status === 'HUMAN_HANDLING'
    const customerId = selected?.customer ?? null

    if (
      ticketId === wsTicketIdRef.current &&
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return
    }

    if (wsRef.current) {
      wsRef.current.onclose = null
      wsRef.current.close()
      wsRef.current = null
    }

    if (ticketId !== wsTicketIdRef.current) {
      setReplyText('')
      setLiveMessages([])
      wsTicketIdRef.current = ticketId
    }

    if (isLive && customerId) {
      const ws = new WebSocket(`${WS_BASE}/ws/chat/${customerId}?token=${encodeURIComponent(token || '')}`)
      wsRef.current = ws
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'message' && data.role === 'user') {
            setLiveMessages(prev => [...prev, { role: 'user', content: data.content }])
          }
        } catch (e) {
          console.error(e)
        }
      }
      ws.onerror = () => console.error('Dashboard WS error')
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [selected?.id, selected?.status, selected?.customer])

  // ── Auto-scroll chat ──────────────────────────────────────────────
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [liveMessages])

  // ── Fetch tickets ─────────────────────────────────────────────────
  const fetchTickets = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/support/tickets`, { headers: authHeaders })
      if (res.status === 401) {
        logout()
        navigate('/login')
        return
      }
      const data: Ticket[] = await res.json()
      setTickets(data)
      setSelected(prev => {
        if (!prev) return data.length > 0 ? data[0] : null
        const fresh = data.find(t => t.id === prev.id)
        return fresh ?? (data.length > 0 ? data[0] : null)
      })
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  // ── Actions ───────────────────────────────────────────────────────
  const handleAccept = async () => {
    if (!selected) return
    const res = await fetch(`${API_BASE}/api/support/tickets/${selected.id}/accept`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders },
      body: JSON.stringify({ staff_name: userName || 'Nhân viên CSKH' }),
    })
    const data = await res.json()
    if (data.error) alert(data.error)
    fetchTickets()
  }

  const handleClose = async () => {
    if (!selected) return
    await fetch(`${API_BASE}/api/support/tickets/${selected.id}/close`, { method: 'POST', headers: authHeaders })
    fetchTickets()
  }

  const handleSendLive = () => {
    if (!replyText.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    const msg = replyText.trim()
    wsRef.current.send(JSON.stringify({ type: 'message', role: 'bot', content: msg }))
    setLiveMessages(prev => [...prev, { role: 'bot', content: msg }])
    setReplyText('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendLive()
    }
  }

  useEffect(() => {
    fetchTickets()
    const interval = setInterval(fetchTickets, 5000)
    return () => clearInterval(interval)
  }, [fetchTickets])

  // ── Helpers ───────────────────────────────────────────────────────
  const filteredTickets = tickets.filter(t => {
    if (filterTab === 'PENDING') return t.status === 'PENDING_ESCALATION'
    if (filterTab === 'HANDLING') return t.status === 'HUMAN_HANDLING' && t.staff_assigned === userName
    if (filterTab === 'RESOLVED') return t.status === 'RESOLVED' && t.staff_assigned === userName
    return true
  })

  const pendingCount = tickets.filter(t => t.status === 'PENDING_ESCALATION').length
  const handlingCount = tickets.filter(t => t.status === 'HUMAN_HANDLING' && t.staff_assigned === userName).length

  const statusDot = (s: string) => {
    if (s === 'PENDING_ESCALATION') return '#ea4335'
    if (s === 'HUMAN_HANDLING') return '#fbbc04'
    if (s === 'RESOLVED') return '#34a853'
    return '#9aa0a6'
  }

  const statusText = (s: string) => {
    if (s === 'PENDING_ESCALATION') return 'Chờ tiếp nhận'
    if (s === 'HUMAN_HANDLING') return 'Đang hỗ trợ'
    if (s === 'RESOLVED') return 'Đã xong'
    return 'AI đang xử lý'
  }

  // ── Tab button component ──────────────────────────────────────────
  const TabBtn = ({ tab, label, count }: { tab: FilterTab; label: string; count?: number }) => (
    <button
      onClick={() => setFilterTab(tab)}
      style={{
        padding: '8px 16px', border: 'none', cursor: 'pointer',
        fontWeight: filterTab === tab ? 600 : 400,
        fontSize: '0.9rem', fontFamily: 'inherit',
        color: filterTab === tab ? '#0b57d0' : '#5f6368',
        background: 'transparent',
        borderBottom: filterTab === tab ? '3px solid #0b57d0' : '3px solid transparent',
        transition: 'all 0.2s',
        display: 'flex', alignItems: 'center', gap: '6px',
      }}
    >
      {label}
      {(count !== undefined && count > 0) && (
        <span style={{
          background: tab === 'PENDING' ? '#ea4335' : '#fbbc04',
          color: '#fff', fontSize: '0.7rem', fontWeight: 700,
          padding: '1px 7px', borderRadius: '10px', minWidth: '18px', textAlign: 'center',
        }}>{count}</span>
      )}
    </button>
  )

  // ── RENDER ─────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#fff' }}>

      {/* ─── Top Header ─── */}
      <header style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 24px', height: '56px', borderBottom: '1px solid #e0e0e0',
        background: '#fff', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            width: '32px', height: '32px', borderRadius: '50%',
            background: 'linear-gradient(135deg, #0b57d0, #8ab4f8)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff',
          }}>
            <MessageCircle size={18} />
          </div>
          <h1 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#1e1e1e' }}>Staff Messenger</h1>
        </div>
        <button
          onClick={() => { logout(); navigate('/login') }}
          style={{
            display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 14px',
            background: '#f1f3f4', border: 'none', borderRadius: '20px', cursor: 'pointer',
            color: '#5f6368', fontSize: '0.85rem', fontWeight: 500,
          }}
        >
          <LogOut size={14} /> Đăng xuất
        </button>
      </header>

      {/* ─── Main Body: Conversation List + Chat Panel ─── */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

        {/* ════════ LEFT: Conversation List ════════ */}
        <div style={{
          width: '360px', borderRight: '1px solid #e0e0e0',
          display: 'flex', flexDirection: 'column', background: '#fff', flexShrink: 0,
        }}>
          {/* Filter tabs */}
          <div style={{
            display: 'flex', borderBottom: '1px solid #e0e0e0', padding: '0 8px',
            background: '#fafafa',
          }}>
            <TabBtn tab="ALL" label="Tất cả" />
            <TabBtn tab="PENDING" label="Cần xử lý" count={pendingCount} />
            <TabBtn tab="HANDLING" label="Đang xử lý" count={handlingCount} />
            <TabBtn tab="RESOLVED" label="Đã xong" />
          </div>

          {/* Conversation items */}
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {filteredTickets.length === 0 ? (
              <div style={{ padding: '48px 24px', textAlign: 'center', color: '#9aa0a6' }}>
                <Inbox size={40} strokeWidth={1.2} style={{ marginBottom: '12px', opacity: 0.5 }} />
                <p style={{ fontSize: '0.9rem' }}>Không có cuộc hội thoại nào</p>
              </div>
            ) : (
              filteredTickets.map(t => (
                <div
                  key={t.id}
                  onClick={() => setSelected(t)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '12px',
                    padding: '14px 16px', cursor: 'pointer',
                    background: selected?.id === t.id ? '#e8f0fe' : 'transparent',
                    borderBottom: '1px solid #f1f3f4',
                    transition: 'background 0.15s',
                  }}
                  onMouseEnter={e => { if (selected?.id !== t.id) e.currentTarget.style.background = '#f8f9fa' }}
                  onMouseLeave={e => { if (selected?.id !== t.id) e.currentTarget.style.background = 'transparent' }}
                >
                  {/* Avatar */}
                  <div style={{
                    width: '48px', height: '48px', borderRadius: '50%', flexShrink: 0,
                    background: '#e8f0fe', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: '#0b57d0', position: 'relative',
                  }}>
                    <User size={22} />
                    {/* Status dot */}
                    <div style={{
                      position: 'absolute', bottom: '1px', right: '1px',
                      width: '12px', height: '12px', borderRadius: '50%',
                      background: statusDot(t.status), border: '2px solid #fff',
                    }} />
                  </div>

                  {/* Info */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{
                        fontWeight: t.status === 'PENDING_ESCALATION' ? 700 : 500,
                        fontSize: '0.95rem', color: '#1e1e1e',
                      }}>
                        {t.customer?.substring(0, 16)}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: '#9aa0a6', flexShrink: 0 }}>{t.createdAt}</span>
                    </div>
                    <div style={{
                      fontSize: '0.85rem', color: '#5f6368', marginTop: '2px',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {t.message || t.type || 'Chưa có tin nhắn'}
                    </div>
                    <span style={{
                      fontSize: '0.7rem', fontWeight: 600,
                      color: statusDot(t.status), marginTop: '2px', display: 'inline-block',
                    }}>
                      {statusText(t.status)}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* ════════ RIGHT: Chat Panel ════════ */}
        {selected ? (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#f8f9fa' }}>

            {/* Chat header */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '12px 24px', background: '#fff', borderBottom: '1px solid #e0e0e0',
              flexShrink: 0,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{
                  width: '40px', height: '40px', borderRadius: '50%',
                  background: '#e8f0fe', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: '#0b57d0',
                }}>
                  <User size={20} />
                </div>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>{selected.customer}</div>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center', fontSize: '0.8rem' }}>
                    <span style={{
                      display: 'inline-flex', alignItems: 'center', gap: '4px',
                      color: statusDot(selected.status), fontWeight: 600,
                    }}>
                      <span style={{
                        width: '7px', height: '7px', borderRadius: '50%',
                        background: statusDot(selected.status), display: 'inline-block',
                      }} />
                      {statusText(selected.status)}
                    </span>
                    {selected.type && <span style={{ color: '#9aa0a6' }}>• {selected.type}</span>}
                    {selected.priority && <span style={{ color: '#ea4335', fontWeight: 600 }}>• {selected.priority}</span>}
                  </div>
                  {selected.escalation_reason && (
                    <div style={{ fontSize: '0.78rem', color: '#c5221f', marginTop: '2px', maxWidth: '420px' }}>
                      Lý do chuyển: {selected.escalation_reason}
                    </div>
                  )}
                </div>
              </div>

              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  onClick={() => setShowLog(!showLog)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 14px',
                    background: showLog ? '#e8f0fe' : '#f1f3f4', border: 'none', borderRadius: '20px',
                    cursor: 'pointer', fontSize: '0.8rem', fontWeight: 500,
                    color: showLog ? '#0b57d0' : '#5f6368',
                  }}
                >
                  <Activity size={14} /> Log AI
                </button>

                {selected.status === 'PENDING_ESCALATION' && !selected.staff_assigned && (
                  <button onClick={handleAccept} style={{
                    display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 16px',
                    background: '#0b57d0', color: '#fff', border: 'none', borderRadius: '20px',
                    fontWeight: 600, cursor: 'pointer', fontSize: '0.85rem',
                  }}>
                    <UserCheck size={14} /> Tiếp nhận
                  </button>
                )}

                {selected.status === 'HUMAN_HANDLING' && selected.staff_assigned === userName && (
                  <button onClick={handleClose} style={{
                    display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 14px',
                    background: '#fce8e6', color: '#c5221f', border: 'none', borderRadius: '20px',
                    fontWeight: 600, cursor: 'pointer', fontSize: '0.85rem',
                  }}>
                    <XCircle size={14} /> Kết thúc
                  </button>
                )}
              </div>
            </div>

            {/* AI Log panel (collapsible) */}
            {showLog && (
              <div style={{
                padding: '12px 24px', background: '#fff3cd', borderBottom: '1px solid #e0e0e0',
                maxHeight: '180px', overflowY: 'auto', flexShrink: 0,
              }}>
                <h4 style={{ fontSize: '0.8rem', color: '#856404', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Activity size={14} /> AI Processing Log
                </h4>
                {(selected.log?.length ?? 0) === 0
                  ? <p style={{ fontSize: '0.8rem', color: '#a07800' }}>Chưa có log.</p>
                  : selected.log.map((l, i) => (
                      <div key={i} style={{ fontSize: '0.78rem', color: '#664d03', marginBottom: '4px', lineHeight: 1.4 }}>{l}</div>
                    ))
                }
              </div>
            )}

            {/* ─── Chat messages area ─── */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {/* System message showing ticket info */}
              <div style={{
                alignSelf: 'center', background: '#e8eaed', padding: '4px 14px',
                borderRadius: '14px', fontSize: '0.78rem', color: '#5f6368', marginBottom: '8px',
              }}>
                Ticket {selected.id?.substring(0, 12)} • {selected.createdAt}
              </div>

              {/* Initial customer message */}
              {selected.message && (
                <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end' }}>
                  <div style={{
                    width: '28px', height: '28px', borderRadius: '50%', flexShrink: 0,
                    background: '#e8f0fe', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: '#0b57d0',
                  }}>
                    <User size={14} />
                  </div>
                  <div style={{
                    background: '#e4e6eb', padding: '10px 14px', borderRadius: '18px',
                    borderBottomLeftRadius: '4px', maxWidth: '70%', fontSize: '0.92rem',
                    lineHeight: 1.45, color: '#1e1e1e',
                  }}>
                    {selected.message}
                  </div>
                </div>
              )}

              {/* Live chat messages */}
              {liveMessages.map((m, i) => (
                <div key={i} style={{
                  display: 'flex', gap: '8px', alignItems: 'flex-end',
                  flexDirection: m.role === 'bot' ? 'row-reverse' : 'row',
                }}>
                  {m.role === 'user' && (
                    <div style={{
                      width: '28px', height: '28px', borderRadius: '50%', flexShrink: 0,
                      background: '#e8f0fe', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: '#0b57d0',
                    }}>
                      <User size={14} />
                    </div>
                  )}
                  <div style={{
                    padding: '10px 14px', borderRadius: '18px', maxWidth: '70%',
                    fontSize: '0.92rem', lineHeight: 1.45,
                    background: m.role === 'bot' ? '#0b57d0' : '#e4e6eb',
                    color: m.role === 'bot' ? '#fff' : '#1e1e1e',
                    borderBottomRightRadius: m.role === 'bot' ? '4px' : '18px',
                    borderBottomLeftRadius: m.role === 'user' ? '4px' : '18px',
                  }}>
                    {m.content}
                  </div>
                </div>
              ))}

              {/* Placeholder when no live messages & HUMAN_HANDLING */}
              {selected.status === 'HUMAN_HANDLING' && liveMessages.length === 0 && (
                <div style={{
                  alignSelf: 'center', color: '#9aa0a6', fontSize: '0.85rem',
                  fontStyle: 'italic', margin: '24px 0',
                }}>
                  Đang chờ tin nhắn từ khách hàng...
                </div>
              )}

              {/* Placeholder when PENDING */}
              {selected.status === 'PENDING_ESCALATION' && (
                <div style={{
                  alignSelf: 'center', color: '#ea4335', fontSize: '0.85rem',
                  fontWeight: 500, margin: '24px 0', textAlign: 'center',
                  padding: '16px 24px', background: '#fce8e6', borderRadius: '12px',
                }}>
                  ⚠️ Khách hàng đang chờ được hỗ trợ. Bấm "Tiếp nhận" để bắt đầu chat.
                </div>
              )}

              {/* Placeholder when RESOLVED */}
              {selected.status === 'RESOLVED' && (
                <div style={{
                  alignSelf: 'center', color: '#34a853', fontSize: '0.85rem',
                  fontWeight: 500, margin: '24px 0', textAlign: 'center',
                  padding: '16px 24px', background: '#e6f4ea', borderRadius: '12px',
                }}>
                  ✅ Case đã được giải quyết xong.
                </div>
              )}

              <div ref={chatEndRef} />
            </div>

            {/* ─── Input bar (Messenger style) ─── */}
            {selected.status === 'HUMAN_HANDLING' && selected.staff_assigned === userName ? (
              <div style={{
                display: 'flex', alignItems: 'center', gap: '10px',
                padding: '12px 20px', background: '#fff', borderTop: '1px solid #e0e0e0',
                flexShrink: 0,
              }}>
                <input
                  type="text"
                  placeholder="Aa"
                  value={replyText}
                  onChange={e => setReplyText(e.target.value)}
                  onKeyDown={handleKeyDown}
                  style={{
                    flex: 1, padding: '10px 18px', borderRadius: '20px',
                    border: '1px solid #e0e0e0', outline: 'none', fontSize: '0.95rem',
                    fontFamily: 'inherit', background: '#f0f2f5',
                  }}
                />
                <button
                  onClick={handleSendLive}
                  disabled={!replyText.trim()}
                  style={{
                    width: '36px', height: '36px', borderRadius: '50%',
                    background: replyText.trim() ? '#0b57d0' : '#e0e0e0',
                    color: '#fff', border: 'none', cursor: replyText.trim() ? 'pointer' : 'default',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0, transition: 'background 0.2s',
                  }}
                >
                  <Send size={16} />
                </button>
              </div>
            ) : (
              <div style={{
                padding: '16px 20px', background: '#fff', borderTop: '1px solid #e0e0e0',
                textAlign: 'center', color: '#9aa0a6', fontSize: '0.85rem', flexShrink: 0,
              }}>
                {selected.status === 'PENDING_ESCALATION'
                  ? 'Bấm "Tiếp nhận" để bắt đầu hỗ trợ khách hàng'
                  : selected.status === 'HUMAN_HANDLING'
                  ? `Case đang được xử lý bởi ${selected.staff_assigned}`
                  : 'Cuộc hội thoại đã kết thúc'
                }
              </div>
            )}
          </div>
        ) : (
          /* No ticket selected */
          <div style={{
            flex: 1, display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', background: '#f8f9fa', color: '#9aa0a6',
          }}>
            <MessageCircle size={56} strokeWidth={1.2} style={{ marginBottom: '16px', opacity: 0.4 }} />
            <p style={{ fontSize: '1.1rem', fontWeight: 500 }}>Chọn một cuộc hội thoại</p>
            <p style={{ fontSize: '0.85rem', marginTop: '4px' }}>để bắt đầu hỗ trợ khách hàng</p>
          </div>
        )}
      </div>
    </div>
  )
}
