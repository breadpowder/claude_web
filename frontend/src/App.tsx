import { useEffect } from 'react'
import './App.css'
import { useStore } from './stores/index.ts'
import { Header } from './components/Header/Header.tsx'
import { ErrorBanner } from './components/ErrorBanner/ErrorBanner.tsx'
import { MessageList } from './components/MessageList/MessageList.tsx'
import { ChatInput } from './components/ChatInput/ChatInput.tsx'

function App() {
  const createSession = useStore(s => s.createSession)

  useEffect(() => {
    createSession()
  }, [createSession])

  return (
    <div className="app">
      <Header />
      <ErrorBanner />
      <MessageList />
      <ChatInput />
    </div>
  )
}

export default App
