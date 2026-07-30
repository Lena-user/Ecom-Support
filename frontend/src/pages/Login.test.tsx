import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '../AuthContext'
import Login from './Login'

describe('Login', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('đăng nhập thành công gọi đúng API và lưu role vào context', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ access_token: 'fake-token', role: 'admin', name: 'Admin' }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <AuthProvider>
          <Login />
        </AuthProvider>
      </MemoryRouter>,
    )

    await user.type(screen.getByPlaceholderText('VD: admin@demo.com'), 'admin@demo.com')
    await user.type(screen.getByPlaceholderText('Nhập 123'), '123')
    await user.click(screen.getByRole('button', { name: /Đăng nhập/ }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/auth/login'),
        expect.objectContaining({ method: 'POST' }),
      )
    })
    await waitFor(() => {
      expect(localStorage.getItem('auth_role')).toBe('admin')
      expect(localStorage.getItem('auth_token')).toBe('fake-token')
    })
  })

  it('hiện thông báo lỗi khi sai mật khẩu', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'Email hoặc mật khẩu không đúng' }),
      })),
    )

    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <AuthProvider>
          <Login />
        </AuthProvider>
      </MemoryRouter>,
    )

    await user.type(screen.getByPlaceholderText('VD: admin@demo.com'), 'admin@demo.com')
    await user.type(screen.getByPlaceholderText('Nhập 123'), 'sai-mat-khau')
    await user.click(screen.getByRole('button', { name: /Đăng nhập/ }))

    expect(await screen.findByText('Email hoặc mật khẩu không đúng')).toBeInTheDocument()
    expect(localStorage.getItem('auth_role')).toBeNull()
  })
})
