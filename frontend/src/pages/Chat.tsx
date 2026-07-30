import { useState, useRef, useEffect } from 'react'
import { ArrowUp, User, Sparkles, ShieldAlert, Headset, Bot } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import { API_BASE, WS_BASE } from '../config'

interface Message {
  id: string;
  role: 'user' | 'bot';
  content: string;
}

// ── Lấy hoặc tạo guestId ổn định, lưu vào sessionStorage ──────────
function getOrCreateGuestId(): string {
  const key = 'ecom_guest_id'
  let id = sessionStorage.getItem(key)
  if (!id) {
    id = 'GUEST_' + Date.now() + '_' + Math.floor(Math.random() * 1000)
    sessionStorage.setItem(key, id)
  }
  return id
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [assignedTo, setAssignedTo] = useState<string | null>(null)
  
  // Guest ID ổn định: giữ nguyên khi refresh/thoát tab rồi mở lại (cùng tab)
  const [guestId] = useState(getOrCreateGuestId)
  
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const msgCounter = useRef(0)
  const closedIntentionally = useRef(false)   // cờ ngăn reconnect khi cleanup
  const navigate = useNavigate()
  const { logout } = useAuth()

  const nextId = () => `msg-${Date.now()}-${++msgCounter.current}`

  // ── Khôi phục session khi quay lại trang ──────────────────────────
  useEffect(() => {
    async function restoreSession() {
      try {
        const res = await fetch(`${API_BASE}/api/support/session/${guestId}`)
        const data = await res.json()
        if (!data.exists) return

        // Khôi phục lịch sử tin nhắn
        if (data.messages?.length > 0) {
          const restored: Message[] = data.messages.map((m: {role: string, content: string}, i: number) => ({
            id: `restored-${i}`,
            role: m.role as 'user' | 'bot',
            content: m.content,
          }))
          setMessages(restored)
        }

        // Khôi phục trạng thái nhân viên đang hỗ trợ
        if (data.status === 'HUMAN_HANDLING' && data.staff_assigned) {
          setAssignedTo(data.staff_assigned)
        }

        // Nếu đang chờ nhân viên
        if (data.status === 'PENDING_ESCALATION') {
          setMessages(prev => {
            // Chỉ thêm nếu chưa có message chờ
            const hasWaiting = prev.some(m => m.content.includes('đang được chuyển đến nhân viên'))
            if (!hasWaiting) {
              return [...prev, { id: nextId(), role: 'bot', content: 'Yêu cầu của bạn đang được chuyển đến nhân viên hỗ trợ, vui lòng chờ trong giây lát.' }]
            }
            return prev
          })
        }
      } catch (err) {
        console.error('Restore session failed:', err)
      }
    }
    restoreSession()
  }, [guestId])

  // ── WebSocket lifecycle ──────────────────────────────────────────
  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout>
    closedIntentionally.current = false

    function connect() {
      if (closedIntentionally.current) return   // đã cleanup, không reconnect nữa

      const ws = new WebSocket(`${WS_BASE}/ws/chat/${guestId}`)
      wsRef.current = ws

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'session:assigned') {
            setAssignedTo(data.assigned_to)
          } else if (data.type === 'session:resolved') {
            setAssignedTo(null)
            setMessages(prev => [...prev, { id: nextId(), role: 'bot', content: 'Cuộc trò chuyện đã kết thúc. Cảm ơn bạn đã liên hệ!' }])
          } else if (data.type === 'message' && data.role === 'bot') {
            setMessages(prev => [...prev, { id: nextId(), role: 'bot', content: data.content }])
            setLoading(false)
          }
        } catch (err) {
          console.error(err)
        }
      }

      ws.onclose = () => {
        if (!closedIntentionally.current) {
          reconnectTimer = setTimeout(connect, 2000)
        }
      }
    }

    connect()

    return () => {
      closedIntentionally.current = true        // đánh dấu đóng có chủ đích
      clearTimeout(reconnectTimer)
      if (wsRef.current) {
        wsRef.current.onclose = null            // gỡ handler để không trigger reconnect
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [guestId])

  // ── Scroll ───────────────────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // ── Send message ─────────────────────────────────────────────────
  const handleSend = async (text: string = input) => {
    if (!text.trim()) return

    const userMsg = text.trim()
    setInput('')
    
    setMessages(prev => [...prev, { id: nextId(), role: 'user', content: userMsg }])
    
    // Nếu đang được nhân viên hỗ trợ → gửi qua WS, KHÔNG qua AI pipeline
    if (assignedTo && wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'message', role: 'user', content: userMsg }))
      return
    }

    // Gửi qua AI pipeline
    setLoading(true)
    try {
      const response = await fetch(`${API_BASE}/api/support/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_id: guestId,
          channel: 'web_chat',
          message: userMsg
        })
      })

      const data = await response.json()
      
      if (data.status === 'PENDING_ESCALATION') {
        setMessages(prev => [...prev, { id: nextId(), role: 'bot', content: 'Yêu cầu của bạn đang được chuyển đến nhân viên hỗ trợ, vui lòng chờ trong giây lát.' }])
      } else {
        setMessages(prev => [...prev, { id: nextId(), role: 'bot', content: data.response || 'Xin lỗi, đã có lỗi xảy ra.' }])
      }
    } catch (error) {
      setMessages(prev => [...prev, { id: nextId(), role: 'bot', content: 'Lỗi kết nối đến máy chủ API.' }])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const suggestions = [
    "Chính sách đổi trả hàng như thế nào?",
    "Đơn hàng của tôi bao giờ giao?",
    "Sản phẩm bị lỗi tôi muốn hoàn tiền",
    "Phí vận chuyển tính ra sao?"
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', backgroundColor: '#fff', alignItems: 'center' }}>
      <header style={{ width: '100%', padding: '16px 24px', display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #eaeaea', position: 'absolute', top: 0, zIndex: 10, background: 'rgba(255,255,255,0.9)', backdropFilter: 'blur(8px)' }}>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <h1 style={{ fontSize: '1.2rem', fontWeight: 600, color: '#1e1e1e' }}>Robin - Support Assistant</h1>
          {assignedTo && (
            <span style={{ fontSize: '0.85rem', color: '#137333', display: 'flex', alignItems: 'center', gap: '4px', fontWeight: 500 }}>
              <Headset size={14} /> Bạn đang được hỗ trợ bởi {assignedTo}
            </span>
          )}
        </div>
        <button onClick={() => { logout(); navigate('/login'); }} style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#444746', background: 'transparent', border: 'none', cursor: 'pointer', fontWeight: 500, fontSize: '0.9rem' }}>
          <ShieldAlert size={16} /> Cổng Nhân viên
        </button>
      </header>

      <main style={{ flex: 1, width: '100%', maxWidth: '800px', display: 'flex', flexDirection: 'column', paddingTop: '70px', paddingBottom: '120px', position: 'relative', overflow: 'hidden' }}>
        
        {messages.length === 0 ? (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '0 20px' }}>
            <img src="/robin.jpg" alt="Robin" style={{ width: '60px', height: '60px', borderRadius: '16px', marginBottom: '24px', objectFit: 'cover', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }} />
            <h2 style={{ fontSize: '1.5rem', fontWeight: 500, color: '#1e1e1e', marginBottom: '32px' }}>Hi, I'm Robin. How can I help you today?</h2>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', width: '100%', maxWidth: '600px' }}>
              {suggestions.map((s, i) => (
                <button key={i} onClick={() => handleSend(s)} style={{ padding: '16px', textAlign: 'left', background: '#f4f7fb', border: '1px solid #e8f0fe', borderRadius: '12px', cursor: 'pointer', color: '#444746', fontSize: '0.95rem', transition: 'all 0.2s' }} onMouseOver={e => e.currentTarget.style.background = '#e8f0fe'} onMouseOut={e => e.currentTarget.style.background = '#f4f7fb'}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div style={{ flex: 1, overflowY: 'auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: '32px' }}>
            {messages.map(msg => (
              <div key={msg.id} style={{ display: 'flex', gap: '16px', flexDirection: msg.role === 'user' ? 'row-reverse' : 'row' }}>
                <div style={{ width: '36px', height: '36px', borderRadius: '50%', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: msg.role === 'bot' ? (assignedTo ? '#137333' : 'transparent') : '#f0f4f9', color: msg.role === 'bot' ? '#fff' : '#444746', overflow: 'hidden' }}>
                  {msg.role === 'bot' ? (assignedTo ? <Headset size={20} /> : <img src="/robin.jpg" alt="Robin" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />) : <User size={20} />}
                </div>
                
                <div style={{ 
                  padding: msg.role === 'user' ? '12px 20px' : '6px 0', 
                  background: msg.role === 'user' ? '#e8f0fe' : 'transparent',
                  color: '#1e1e1e',
                  borderRadius: '24px',
                  borderBottomRightRadius: msg.role === 'user' ? '4px' : '24px',
                  fontSize: '1rem',
                  lineHeight: '1.6',
                  maxWidth: '80%',
                  whiteSpace: 'pre-wrap'
                }}>
                  {msg.content}
                </div>
              </div>
            ))}
            
            {loading && (
              <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                <div style={{ width: '36px', height: '36px', borderRadius: '50%', flexShrink: 0, overflow: 'hidden' }}>
                  <img src="/robin.jpg" alt="Robin" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                </div>
                <div style={{ padding: '6px 0' }} className="typing-dots">
                  <div className="dot"></div><div className="dot"></div><div className="dot"></div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}

        <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, padding: '24px', background: 'linear-gradient(to top, white 80%, transparent)', pointerEvents: 'none' }}>
          <div style={{ 
            background: '#f4f7fb', borderRadius: '24px', padding: '14px 64px 14px 24px', position: 'relative', 
            border: '1px solid #e0e0e0', boxShadow: '0 4px 12px rgba(0,0,0,0.03)', pointerEvents: 'auto',
            display: 'flex', alignItems: 'center'
          }}>
            <textarea
              placeholder="Ask me anything..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              style={{ width: '100%', background: 'transparent', border: 'none', outline: 'none', fontSize: '1rem', resize: 'none', maxHeight: '120px', minHeight: '24px', padding: 0, fontFamily: 'inherit', color: '#1e1e1e', lineHeight: '24px' }}
              rows={1}
            />
            {input.trim() && (
              <button 
                onClick={() => handleSend()}
                disabled={loading}
                style={{ position: 'absolute', right: '12px', bottom: '8px', background: '#1e1e1e', color: '#fff', border: 'none', borderRadius: '50%', width: '32px', height: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
              >
                <ArrowUp size={18} strokeWidth={2.5} />
              </button>
            )}
          </div>
          <p style={{ textAlign: 'center', fontSize: '0.75rem', color: '#888', marginTop: '12px' }}>AI can make mistakes. Verify important information.</p>
        </div>
      </main>
    </div>
  )
}
