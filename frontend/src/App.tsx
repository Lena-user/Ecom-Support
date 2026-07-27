import React from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import Chat from './pages/Chat'
import Dashboard from './pages/Dashboard'
import Admin from './pages/Admin'
import Login from './pages/Login'
import { AuthProvider, useAuth } from './AuthContext'
import type { Role } from './AuthContext'

function ProtectedRoute({ children, allowedRoles }: { children: React.ReactNode, allowedRoles: Role[] }) {
  const { userRole } = useAuth()
  
  if (!userRole) {
    return <Navigate to="/login" replace />
  }
  
  if (!allowedRoles.includes(userRole)) {
    // If not allowed, redirect to their home page
    if (userRole === 'admin') return <Navigate to="/admin" replace />
    if (userRole === 'staff') return <Navigate to="/dashboard" replace />
    return <Navigate to="/" replace />
  }
  
  return children
}

export default function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<Login />} />
          
          {/* Public route */}
          <Route path="/chat" element={<Chat />} />
          
          {/* Protected routes */}
          <Route path="/dashboard" element={
            <ProtectedRoute allowedRoles={['staff']}>
              <Dashboard />
            </ProtectedRoute>
          } />
          
          <Route path="/admin" element={
            <ProtectedRoute allowedRoles={['admin']}>
              <Admin />
            </ProtectedRoute>
          } />
          
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
      </Router>
    </AuthProvider>
  )
}
