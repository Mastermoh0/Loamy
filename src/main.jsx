import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from "react-router-dom";

// Root app (holds routes + the global activity-sync wrapper)
import App from './App.jsx'

// Styles
import './index.css'
// Loaded last so the phone-scale and native-shell rules win over page CSS.
import './native.css'

// Native apps don't show a link preview or start a link drag on long-press.
// Text fields and anything marked .selectable keep the system menu (copy/paste).
const keepsSystemMenu = (target) =>
  target instanceof Element && target.closest('input, textarea, [contenteditable="true"], .selectable')

document.addEventListener('contextmenu', (e) => {
  if (!keepsSystemMenu(e.target)) e.preventDefault()
})

document.addEventListener('dragstart', (e) => {
  if (!keepsSystemMenu(e.target)) e.preventDefault()
})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
