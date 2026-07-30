import { createContext, useContext, useState } from 'react'
import type { ReactNode } from 'react'
import { API_BASE } from './config'

export type Role = 'customer' | 'staff' | 'admin' | null;

interface AuthContextType {
  userRole: Role;
  userName: string | null;
  userEmail: string | null;
  token: string | null;
  login: (email: string, password: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  userRole: null,
  userName: null,
  userEmail: null,
  token: null,
  login: async () => ({ success: false }),
  logout: () => {}
})

export const useAuth = () => useContext(AuthContext)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [userRole, setUserRole] = useState<Role>(() => {
    const saved = localStorage.getItem('auth_role')
    return (saved as Role) || null
  })
  const [userName, setUserName] = useState<string | null>(() => localStorage.getItem('auth_name'))
  const [userEmail, setUserEmail] = useState<string | null>(() => localStorage.getItem('auth_email'))
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('auth_token'))

  const login = async (email: string, password: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        return { success: false, error: data.detail || 'Email hoặc mật khẩu không đúng' }
      }
      const data = await res.json()
      setUserRole(data.role)
      setUserName(data.name)
      setUserEmail(email)
      setToken(data.access_token)
      localStorage.setItem('auth_role', data.role)
      localStorage.setItem('auth_name', data.name)
      localStorage.setItem('auth_email', email)
      localStorage.setItem('auth_token', data.access_token)
      return { success: true }
    } catch {
      return { success: false, error: 'Lỗi kết nối đến máy chủ API.' }
    }
  }

  const logout = () => {
    setUserRole(null)
    setUserName(null)
    setUserEmail(null)
    setToken(null)
    localStorage.removeItem('auth_role')
    localStorage.removeItem('auth_name')
    localStorage.removeItem('auth_email')
    localStorage.removeItem('auth_token')
  }

  return (
    <AuthContext.Provider value={{ userRole, userName, userEmail, token, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
