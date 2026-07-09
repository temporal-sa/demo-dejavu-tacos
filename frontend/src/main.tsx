import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// Ephemeral per-page-load session id. Lives only in memory, so a reload starts a
// fresh session (and thus fresh "cable" connectivity state). Not persisted to
// sessionStorage/localStorage on purpose.
const SESSION_ID = crypto.randomUUID()

// Attach the session id to every same-origin /api request so the backend can
// scope store connectivity (and the KDS order list) per browser tab. Wrapping
// fetch once here keeps the individual components untouched.
const nativeFetch = window.fetch.bind(window)
window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
  const url =
    typeof input === 'string'
      ? input
      : input instanceof URL
        ? input.pathname
        : input.url
  if (url.startsWith('/api/')) {
    const headers = new Headers(
      init?.headers ?? (input instanceof Request ? input.headers : undefined)
    )
    headers.set('X-Session-Id', SESSION_ID)
    init = { ...init, headers }
  }
  return nativeFetch(input, init)
}

// Tell the backend to drop this session the moment the tab is closed or the user
// navigates away. sendBeacon can't set custom headers, so the id rides in the URL.
window.addEventListener('pagehide', () => {
  navigator.sendBeacon(`/api/session/end?session_id=${encodeURIComponent(SESSION_ID)}`)
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
