import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/chat/new" replace />} />
        <Route path="/chat/*" element={<App />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
