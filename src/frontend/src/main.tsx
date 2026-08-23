import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router/dom'
import { AuthProvider } from './auth/AuthContext'
import { router } from './router'
import './styles.css'

/**
 * `AuthProvider` wraps the router, not the other way round: the guards inside the route tree call
 * `useAuth()`, so the session has to be readable above every route.
 */
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  </StrictMode>,
)
