import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import { Lock, ArrowLeft } from 'lucide-react'

export default function Login() {
  const [email, setEmail] = useState('')
  const [pass, setPass] = useState('')
  const [error, setError] = useState('')
  
  const { login, userRole } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (userRole === 'admin') navigate('/admin', { replace: true })
    if (userRole === 'staff') navigate('/dashboard', { replace: true })
  }, [userRole, navigate])

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault()
    
    if (login(email, pass)) {
      const userObj = {
        'admin@demo.com': '/admin',
        'staff@demo.com': '/dashboard',
        'staff2@demo.com': '/dashboard'
      } as Record<string, string>
      
      navigate(userObj[email] || '/')
    } else {
      setError('Tài khoản hoặc mật khẩu không đúng')
    }
  }

  return (
    <div style={{ display: 'flex', height: '100vh', width: '100vw', alignItems: 'center', justifyContent: 'center', background: '#f4f7fb', position: 'relative' }}>
      <button onClick={() => navigate('/chat')} style={{ position: 'absolute', top: '24px', left: '24px', display: 'flex', alignItems: 'center', gap: '8px', padding: '12px', background: 'transparent', border: 'none', cursor: 'pointer', color: '#444746', fontSize: '0.9rem', fontWeight: 500 }}>
        <ArrowLeft size={16} /> Về trang Khách hàng
      </button>

      <div style={{ background: '#fff', padding: '40px', borderRadius: '24px', boxShadow: '0 10px 25px rgba(0,0,0,0.05)', width: '100%', maxWidth: '400px' }}>
        <div style={{ textAlign: 'center', marginBottom: '32px' }}>
          <div style={{ width: '48px', height: '48px', background: '#e8f0fe', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#0b57d0', margin: '0 auto 16px' }}>
            <Lock size={24} />
          </div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 600, color: '#1e1e1e' }}>Cổng Nội Bộ</h1>
          <p style={{ color: '#888', fontSize: '0.9rem', marginTop: '8px' }}>E-commerce Support Platform</p>
        </div>

        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {error && <div style={{ color: '#c5221f', background: '#fce8e6', padding: '12px', borderRadius: '8px', fontSize: '0.9rem', textAlign: 'center' }}>{error}</div>}
          
          <div>
            <label style={{ display: 'block', fontSize: '0.9rem', fontWeight: 500, marginBottom: '8px', color: '#444746' }}>Email</label>
            <input 
              type="email" 
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="VD: admin@demo.com"
              style={{ width: '100%', padding: '12px 16px', borderRadius: '8px', border: '1px solid #e0e0e0', fontSize: '1rem', outline: 'none' }} 
            />
          </div>
          
          <div>
            <label style={{ display: 'block', fontSize: '0.9rem', fontWeight: 500, marginBottom: '8px', color: '#444746' }}>Mật khẩu</label>
            <input 
              type="password" 
              required
              value={pass}
              onChange={e => setPass(e.target.value)}
              placeholder="Nhập 123"
              style={{ width: '100%', padding: '12px 16px', borderRadius: '8px', border: '1px solid #e0e0e0', fontSize: '1rem', outline: 'none' }} 
            />
          </div>

          <button type="submit" style={{ width: '100%', padding: '14px', background: '#0b57d0', color: 'white', border: 'none', borderRadius: '8px', fontSize: '1rem', fontWeight: 600, cursor: 'pointer', marginTop: '8px' }}>
            Đăng nhập
          </button>
        </form>

        <div style={{ marginTop: '32px', padding: '16px', background: '#f8f9fa', borderRadius: '8px', fontSize: '0.85rem', color: '#444746' }}>
          <strong>Tài khoản Demo (Pass chung: 123):</strong>
          <ul style={{ paddingLeft: '20px', margin: '8px 0 0 0' }}>
            <li style={{ marginBottom: '4px' }}>CSKH 1: <code>staff@demo.com</code> (Linh Nguyễn)</li>
            <li style={{ marginBottom: '4px' }}>CSKH 2: <code>staff2@demo.com</code> (Minh Trần)</li>
            <li>Admin: <code>admin@demo.com</code></li>
          </ul>
        </div>
      </div>
    </div>
  )
}
