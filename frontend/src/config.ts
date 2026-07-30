const rawBase = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export const API_BASE = rawBase.replace(/\/$/, '')
export const WS_BASE = API_BASE.replace(/^http/, 'ws')
