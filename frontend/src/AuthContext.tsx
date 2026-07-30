import { createContext, useContext, useState } from 'react'
import type { ReactNode } from 'react'

export type Role = 'customer' | 'staff' | 'admin' | null;

interface AuthContextType {
  userRole: Role;
  userName: string | null;
  userEmail: string | null;
  login: (email: string, pass: string) => boolean;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  userRole: null,
  userName: null,
  userEmail: null,
  login: () => false,
  logout: () => {}
})

export const useAuth = () => useContext(AuthContext)

const MOCK_USERS: Record<string, { pass: string, role: Role, name: string }> = {
  'admin@demo.com': { pass: '123', role: 'admin', name: 'Admin' },
  'staff@demo.com': { pass: '123', role: 'staff', name: 'Linh Nguyễn' },
  'staff2@demo.com': { pass: '123', role: 'staff', name: 'Minh Trần' },
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [userRole, setUserRole] = useState<Role>(() => {
    const saved = localStorage.getItem('auth_role')
    return (saved as Role) || null
  })
  const [userName, setUserName] = useState<string | null>(() => localStorage.getItem('auth_name'))
  const [userEmail, setUserEmail] = useState<string | null>(() => localStorage.getItem('auth_email'))

  const login = (email: string, pass: string) => {
    const user = MOCK_USERS[email]
    if (user && user.pass === pass) {
      setUserRole(user.role)
      setUserName(user.name)
      setUserEmail(email)
      localStorage.setItem('auth_role', user.role!)
      localStorage.setItem('auth_name', user.name)
      localStorage.setItem('auth_email', email)
      return true
    }
    return false
  }

  const logout = () => {
    setUserRole(null)
    setUserName(null)
    setUserEmail(null)
    localStorage.removeItem('auth_role')
    localStorage.removeItem('auth_name')
    localStorage.removeItem('auth_email')
  }

  return (
    <AuthContext.Provider value={{ userRole, userName, userEmail, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
