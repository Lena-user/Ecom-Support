import { useState, useRef, useEffect } from 'react'
import { ArrowUp, User, ShieldAlert, Headset, ThumbsUp, ThumbsDown, Paperclip, X, Plus } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useAuth } from '../AuthContext'
import { API_BASE, WS_BASE } from '../config'

interface Message {
  id: string;
  role: 'user' | 'bot';
  content: string;
  sender?: 'ai' | 'staff'; // chỉ có ý nghĩa khi role === 'bot' — quyết định avatar hiển thị
  attachment_url?: string;
}

// ── Lấy hoặc tạo guestId ổn định, lưu vào sessionStorage ──────────
const GUEST_ID_KEY = 'ecom_guest_id'

function getOrCreateGuestId(): string {
  let id = sessionStorage.getItem(GUEST_ID_KEY)
  if (!id) {
    id = 'GUEST_' + Date.now() + '_' + Math.floor(Math.random() * 1000)
    sessionStorage.setItem(GUEST_ID_KEY, id)
  }
  return id
}

// Luôn tạo mới (không đọc lại id cũ) — dùng khi khách bấm "Cuộc hội thoại mới"
function createNewGuestId(): string {
  const id = 'GUEST_' + Date.now() + '_' + Math.floor(Math.random() * 1000)
  sessionStorage.setItem(GUEST_ID_KEY, id)
  return id
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [assignedTo, setAssignedTo] = useState<string | null>(null)
  const [showRating, setShowRating] = useState(false)
  const [ratedValue, setRatedValue] = useState<'up' | 'down' | null>(null)
  const [attachedFile, setAttachedFile] = useState<File | null>(null)
  const [attachedPreview, setAttachedPreview] = useState<string | null>(null)

  // Guest ID ổn định: giữ nguyên khi refresh/thoát tab rồi mở lại (cùng tab)
  const [guestId, setGuestId] = useState(getOrCreateGuestId)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const msgCounter = useRef(0)
  const closedIntentionally = useRef(false)   // cờ ngăn reconnect khi cleanup
  const fileInputRef = useRef<HTMLInputElement>(null)
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
          const restored: Message[] = data.messages.map((m: {role: string, content: string, sender?: 'ai' | 'staff', attachment_url?: string}, i: number) => ({
            id: `restored-${i}`,
            role: m.role as 'user' | 'bot',
            content: m.content,
            sender: m.sender,
            attachment_url: m.attachment_url ? `${API_BASE}${m.attachment_url}` : undefined,
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
              return [...prev, { id: nextId(), role: 'bot', content: 'Yêu cầu của bạn đang được chuyển đến nhân viên hỗ trợ, vui lòng chờ trong giây lát.', sender: 'ai' }]
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
            setMessages(prev => [...prev, { id: nextId(), role: 'bot', content: 'Cuộc trò chuyện đã kết thúc. Cảm ơn bạn đã liên hệ!', sender: 'ai' }])
            setRatedValue(null)
            setShowRating(true)
          } else if (data.type === 'message' && data.role === 'bot') {
            // Tin nhắn role=bot qua WS luôn do nhân viên gửi (Dashboard) — AI trả lời qua /submit, không qua WS
            setMessages(prev => [...prev, { id: nextId(), role: 'bot', content: data.content, sender: 'staff' }])
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

  // ── Đính kèm ảnh ─────────────────────────────────────────────────
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setAttachedFile(file)
    setAttachedPreview(URL.createObjectURL(file))
  }

  const clearAttachment = () => {
    if (attachedPreview) URL.revokeObjectURL(attachedPreview)
    setAttachedFile(null)
    setAttachedPreview(null)
  }

  // ── Send message ─────────────────────────────────────────────────
  const handleSend = async (text: string = input) => {
    const userMsg = text.trim()
    if (!userMsg && !attachedFile) return

    const fileToSend = attachedFile
    const previewToSend = attachedPreview ?? undefined
    setInput('')
    setShowRating(false)
    setRatedValue(null)
    setAttachedFile(null)
    setAttachedPreview(null)

    setMessages(prev => [...prev, { id: nextId(), role: 'user', content: userMsg, attachment_url: previewToSend }])

    // Nếu đang được nhân viên hỗ trợ → gửi qua WS, KHÔNG qua AI pipeline
    if (assignedTo && wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'message', role: 'user', content: userMsg }))
      return
    }

    // Gửi qua AI pipeline
    setLoading(true)
    try {
      let attachmentUrl: string | undefined
      if (fileToSend) {
        const form = new FormData()
        form.append('file', fileToSend)
        const uploadRes = await fetch(`${API_BASE}/api/support/upload`, { method: 'POST', body: form })
        if (uploadRes.ok) {
          const uploadData = await uploadRes.json()
          attachmentUrl = uploadData.url
        }
      }

      const response = await fetch(`${API_BASE}/api/support/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_id: guestId,
          channel: 'web_chat',
          message: userMsg || '(Đã gửi ảnh đính kèm)',
          attachment_url: attachmentUrl,
        })
      })

      const data = await response.json()

      if (data.status === 'PENDING_ESCALATION') {
        setMessages(prev => [...prev, { id: nextId(), role: 'bot', content: 'Yêu cầu của bạn đang được chuyển đến nhân viên hỗ trợ, vui lòng chờ trong giây lát.', sender: 'ai' }])
      } else {
        setMessages(prev => [...prev, { id: nextId(), role: 'bot', content: data.response || 'Xin lỗi, đã có lỗi xảy ra.', sender: 'ai' }])
        setShowRating(true)
      }
    } catch (error) {
      console.error(error)
      setMessages(prev => [...prev, { id: nextId(), role: 'bot', content: 'Lỗi kết nối đến máy chủ API.', sender: 'ai' }])
    } finally {
      setLoading(false)
    }
  }

  const handleRate = async (rating: 'up' | 'down') => {
    setRatedValue(rating)
    try {
      await fetch(`${API_BASE}/api/support/tickets/${guestId}/rate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rating }),
      })
    } catch (err) {
      console.error('Rate ticket failed:', err)
    }
  }

  // ── Bắt đầu cuộc hội thoại mới ─────────────────────────────────────
  const handleNewConversation = () => {
    clearAttachment()
    setInput('')
    setMessages([])
    setAssignedTo(null)
    setShowRating(false)
    setRatedValue(null)
    setLoading(false)
    setGuestId(createNewGuestId())
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {messages.length > 0 && !assignedTo && (
            <button onClick={handleNewConversation} style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#444746', background: 'transparent', border: 'none', cursor: 'pointer', fontWeight: 500, fontSize: '0.9rem' }}>
              <Plus size={16} /> Cuộc hội thoại mới
            </button>
          )}
          <button onClick={() => { logout(); navigate('/login'); }} style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#444746', background: 'transparent', border: 'none', cursor: 'pointer', fontWeight: 500, fontSize: '0.9rem' }}>
            <ShieldAlert size={16} /> Cổng Nhân viên
          </button>
        </div>
      </header>

      <main style={{ flex: 1, width: '100%', maxWidth: '800px', display: 'flex', flexDirection: 'column', paddingTop: '70px', paddingBottom: '120px', position: 'relative', overflow: 'hidden' }}>
        
        {messages.length === 0 ? (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '0 20px' }}>
            <img src="/robin.jpg" alt="Robin" style={{ width: '60px', height: '60px', borderRadius: '16px', marginBottom: '24px', objectFit: 'cover', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }} />
            <h2 style={{ fontSize: '1.5rem', fontWeight: 500, color: '#1e1e1e', marginBottom: '32px' }}>Xin chào, mình là Robin. Mình có thể giúp gì cho bạn hôm nay?</h2>
            
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
                <div style={{ width: '36px', height: '36px', borderRadius: '50%', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: msg.role === 'bot' ? (msg.sender === 'staff' ? '#137333' : 'transparent') : '#f0f4f9', color: msg.role === 'bot' ? '#fff' : '#444746', overflow: 'hidden' }}>
                  {msg.role === 'bot' ? (msg.sender === 'staff' ? <Headset size={20} /> : <img src="/robin.jpg" alt="Robin" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />) : <User size={20} />}
                </div>
                
                <div style={{
                  display: 'flex', flexDirection: 'column', gap: '6px',
                  alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
                  maxWidth: '80%',
                }}>
                  {msg.attachment_url && (
                    <a href={msg.attachment_url} target="_blank" rel="noreferrer">
                      <img
                        src={msg.attachment_url}
                        alt="Ảnh đính kèm"
                        style={{ maxWidth: '260px', maxHeight: '260px', borderRadius: '16px', display: 'block', cursor: 'zoom-in', boxShadow: '0 1px 4px rgba(0,0,0,0.15)' }}
                      />
                    </a>
                  )}
                  {msg.content && (
                    <div style={{
                      padding: msg.role === 'user' ? '12px 20px' : '6px 0',
                      background: msg.role === 'user' ? '#e8f0fe' : 'transparent',
                      color: '#1e1e1e',
                      borderRadius: '24px',
                      borderBottomRightRadius: msg.role === 'user' ? '4px' : '24px',
                      fontSize: '1rem',
                      lineHeight: '1.6',
                      whiteSpace: msg.role === 'user' ? 'pre-wrap' : 'normal'
                    }}>
                      {msg.role === 'bot' ? (
                        <div className="markdown-content">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                        </div>
                      ) : msg.content}
                    </div>
                  )}
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

            {showRating && !loading && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', paddingLeft: '52px', fontSize: '0.88rem', color: '#5f6368' }}>
                {ratedValue ? (
                  <span>Cảm ơn bạn đã đánh giá!</span>
                ) : (
                  <>
                    <span>Câu trả lời có hữu ích không?</span>
                    <button
                      onClick={() => handleRate('up')}
                      aria-label="Hữu ích"
                      style={{ background: '#f4f7fb', border: '1px solid #e0e0e0', borderRadius: '50%', width: '32px', height: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#137333' }}
                    >
                      <ThumbsUp size={16} />
                    </button>
                    <button
                      onClick={() => handleRate('down')}
                      aria-label="Không hữu ích"
                      style={{ background: '#f4f7fb', border: '1px solid #e0e0e0', borderRadius: '50%', width: '32px', height: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#c5221f' }}
                    >
                      <ThumbsDown size={16} />
                    </button>
                  </>
                )}
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}

        <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, padding: '24px', background: 'linear-gradient(to top, white 80%, transparent)', pointerEvents: 'none' }}>
          <input
            type="file"
            accept="image/*"
            ref={fileInputRef}
            onChange={handleFileSelect}
            hidden
          />
          <div style={{ maxWidth: 'none', pointerEvents: 'auto' }}>
            {attachedPreview && (
              <div style={{ display: 'inline-flex', position: 'relative', marginBottom: '8px' }}>
                <img src={attachedPreview} alt="Xem trước ảnh đính kèm" style={{ width: '64px', height: '64px', objectFit: 'cover', borderRadius: '10px', border: '1px solid #e0e0e0' }} />
                <button
                  onClick={clearAttachment}
                  aria-label="Bỏ ảnh đính kèm"
                  style={{ position: 'absolute', top: '-6px', right: '-6px', background: '#1e1e1e', color: '#fff', border: 'none', borderRadius: '50%', width: '20px', height: '20px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
                >
                  <X size={12} />
                </button>
              </div>
            )}
          </div>
          <div style={{
            background: '#f4f7fb', borderRadius: '24px', padding: '10px 12px 10px 16px',
            border: '1px solid #e0e0e0', boxShadow: '0 4px 12px rgba(0,0,0,0.03)', pointerEvents: 'auto',
            display: 'flex', alignItems: 'center', gap: '8px'
          }}>
            <button
              onClick={() => fileInputRef.current?.click()}
              aria-label="Đính kèm ảnh"
              disabled={loading}
              style={{ flexShrink: 0, width: '24px', height: '24px', background: 'transparent', border: 'none', color: '#5f6368', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0 }}
            >
              <Paperclip size={20} />
            </button>
            <textarea
              placeholder="Hỏi mình bất cứ điều gì..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              style={{ flex: 1, minWidth: 0, background: 'transparent', border: 'none', outline: 'none', fontSize: '1rem', resize: 'none', maxHeight: '120px', minHeight: '24px', padding: 0, fontFamily: 'inherit', color: '#1e1e1e', lineHeight: '24px' }}
              rows={1}
            />
            {(input.trim() || attachedFile) && (
              <button
                onClick={() => handleSend()}
                disabled={loading}
                style={{ flexShrink: 0, background: '#1e1e1e', color: '#fff', border: 'none', borderRadius: '50%', width: '32px', height: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
              >
                <ArrowUp size={18} strokeWidth={2.5} />
              </button>
            )}
          </div>
          <p style={{ textAlign: 'center', fontSize: '0.75rem', color: '#888', marginTop: '12px' }}>AI có thể mắc sai sót. Hãy kiểm tra lại thông tin quan trọng.</p>
        </div>
      </main>
    </div>
  )
}
