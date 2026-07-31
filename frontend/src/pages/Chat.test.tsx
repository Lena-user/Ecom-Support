import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '../AuthContext'
import Chat from './Chat'

class FakeWebSocket {
  url: string
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  readyState = 1

  constructor(url: string) {
    this.url = url
  }
  send() {}
  close() {
    this.readyState = 3
  }
}

describe('Chat', () => {
  beforeEach(() => {
    vi.stubGlobal('WebSocket', FakeWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/api/support/session/')) {
          return { ok: true, status: 200, json: async () => ({ exists: false }) }
        }
        if (url.includes('/api/support/submit')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              status: 'RESOLVED',
              response: 'Sản phẩm được đổi trả trong vòng 7 ngày.',
            }),
          }
        }
        return { ok: true, status: 200, json: async () => ({}) }
      }),
    )
  })

  it('gửi câu hỏi gợi ý và hiển thị phản hồi từ bot', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <AuthProvider>
          <Chat />
        </AuthProvider>
      </MemoryRouter>,
    )

    const suggestion = await screen.findByText('Chính sách đổi trả hàng như thế nào?')
    await user.click(suggestion)

    expect(await screen.findByText('Chính sách đổi trả hàng như thế nào?')).toBeInTheDocument()
    expect(await screen.findByText(/Sản phẩm được đổi trả trong vòng 7 ngày/)).toBeInTheDocument()
  })
})
