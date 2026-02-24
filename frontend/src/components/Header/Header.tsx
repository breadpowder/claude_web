import { useState } from 'react'
import { useStore } from '../../stores/index.ts'
import './Header.css'

export function Header() {
  const sessionId = useStore(s => s.sessionId)
  const isConnected = useStore(s => s.isConnected)
  const extensions = useStore(s => s.extensions)

  const [showExtDropdown, setShowExtDropdown] = useState(false)

  const sessionPreview = sessionId ? sessionId.slice(0, 8) : ''

  return (
    <header className="header">
      <div className="header-left">
        <h1 className="header-title">Claude Chat</h1>
        <div className="connection-status">
          <span className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`} />
          <span>{isConnected ? 'Connected' : 'Disconnected'}</span>
        </div>
        {sessionPreview && <span className="session-id">{sessionPreview}</span>}
      </div>

      {extensions && extensions.total_count > 0 && (
        <div className="extension-badge-wrapper">
          <button
            className="extension-badge"
            onClick={() => setShowExtDropdown(prev => !prev)}
          >
            {extensions.total_count} extensions
          </button>
          {showExtDropdown && (
            <div className="extension-dropdown">
              {extensions.mcp_servers.length > 0 && (
                <>
                  <h4>MCP Servers</h4>
                  <ul>
                    {extensions.mcp_servers.map(s => (
                      <li key={s.name}>{s.name}</li>
                    ))}
                  </ul>
                </>
              )}
              {extensions.skills.length > 0 && (
                <>
                  <h4>Skills</h4>
                  <ul>
                    {extensions.skills.map(s => (
                      <li key={s.name}>{s.name}</li>
                    ))}
                  </ul>
                </>
              )}
              {extensions.commands.length > 0 && (
                <>
                  <h4>Commands</h4>
                  <ul>
                    {extensions.commands.map(c => (
                      <li key={c.name}>{c.name}</li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </header>
  )
}
