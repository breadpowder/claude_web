import { useStore } from '../../stores/index.ts'
import './ErrorBanner.css'

export function ErrorBanner() {
  const error = useStore(s => s.error)

  if (!error) return null

  return (
    <div className="error-banner" role="alert">
      {error}
    </div>
  )
}
