import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '../../styles.css'
import './stage2.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
