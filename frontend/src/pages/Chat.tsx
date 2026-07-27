import { useState, useRef, useEffect } from 'react'
import { ArrowUp, User, Sparkles, ShieldAlert } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

interface Message {
  id: string;
  role: 'user' | 'bot';
  content: string;
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  
  const navigate = useNavigate()

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, loading])

  const handleSend = async (text: string = input) => {
    if (!text.trim()) return

    const userMsg = text.trim()
    setInput('')
    
    setMessages(prev => [...prev, { id: Date.now().toString(), role: 'user', content: userMsg }])
    setLoading(true)

    try {
      const response = await fetch('http://localhost:8000/api/support/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_id: 'GUEST_' + Math.floor(Math.random() * 1000),
          channel: 'web_chat',
          message: userMsg
        })
      })

      const data = await response.json()
      setMessages(prev => [...prev, { id: Date.now().toString(), role: 'bot', content: data.response || 'Xin lỗi, đã có lỗi xảy ra.' }])
    } catch (error) {
      setMessages(prev => [...prev, { id: Date.now().toString(), role: 'bot', content: 'Lỗi kết nối đến máy chủ API.' }])
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
        <h1 style={{ fontSize: '1.2rem', fontWeight: 600, color: '#1e1e1e' }}>E-commerce Support</h1>
        <button onClick={() => navigate('/login')} style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#444746', background: 'transparent', border: 'none', cursor: 'pointer', fontWeight: 500, fontSize: '0.9rem' }}>
          <ShieldAlert size={16} /> Cổng Nhân viên
        </button>
      </header>

      <main style={{ flex: 1, width: '100%', maxWidth: '800px', display: 'flex', flexDirection: 'column', paddingTop: '70px', paddingBottom: '120px', position: 'relative' }}>
        
        {messages.length === 0 ? (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '0 20px' }}>
            <div style={{ width: '60px', height: '60px', borderRadius: '16px', background: 'linear-gradient(135deg, #1a73e8, #8ab4f8)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '24px', color: 'white' }}>
              <Sparkles size={32} />
            </div>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 500, color: '#1e1e1e', marginBottom: '32px' }}>How can I help you today?</h2>
            
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
                <div style={{ width: '36px', height: '36px', borderRadius: '50%', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: msg.role === 'bot' ? 'linear-gradient(135deg, #1a73e8, #8ab4f8)' : '#f0f4f9', color: msg.role === 'bot' ? '#fff' : '#444746' }}>
                  {msg.role === 'bot' ? <Sparkles size={20} /> : <User size={20} />}
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
              <div style={{ display: 'flex', gap: '16px' }}>
                <div style={{ width: '36px', height: '36px', borderRadius: '50%', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(135deg, #1a73e8, #8ab4f8)', color: '#fff' }}>
                  <Sparkles size={20} />
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
            background: '#f4f7fb', borderRadius: '24px', padding: '12px 64px 12px 24px', position: 'relative', 
            border: '1px solid #e0e0e0', boxShadow: '0 4px 12px rgba(0,0,0,0.03)', pointerEvents: 'auto' 
          }}>
            <textarea
              placeholder="Ask me anything..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              style={{ width: '100%', background: 'transparent', border: 'none', outline: 'none', fontSize: '1rem', resize: 'none', maxHeight: '120px', minHeight: '24px', padding: 0, fontFamily: 'inherit', color: '#1e1e1e' }}
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
