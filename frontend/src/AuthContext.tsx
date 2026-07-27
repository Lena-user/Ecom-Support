import { createContext, useContext, useState } from 'react'
import type { ReactNode } from 'react'

export type Role = 'customer' | 'staff' | 'admin' | null;

interface AuthContextType {
  userRole: Role;
  login: (email: string, pass: string) => boolean;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  userRole: null,
  login: () => false,
  logout: () => {}
})

export const useAuth = () => useContext(AuthContext)

const MOCK_USERS: Record<string, { pass: string, role: Role }> = {
  'admin@demo.com': { pass: '123', role: 'admin' },
  'staff@demo.com': { pass: '123', role: 'staff' },
}

export function AuthProvider({ children }: { children: ReactNode }) {
  // Try to load from localStorage so refresh doesn't log out
  const [userRole, setUserRole] = useState<Role>(() => {
    const saved = localStorage.getItem('auth_role')
    return (saved as Role) || null
  })

  const login = (email: string, pass: string) => {
    const user = MOCK_USERS[email]
    if (user && user.pass === pass) {
      setUserRole(user.role)
      localStorage.setItem('auth_role', user.role!)
      return true
    }
    return false
  }

  const logout = () => {
    setUserRole(null)
    localStorage.removeItem('auth_role')
  }

  return (
    <AuthContext.Provider value={{ userRole, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
