import ChatBox from '../components/ChatBox'

function Home({ theme, onToggleTheme }) {
  return (
    <div className="page-shell">
      <header className="page-header">
        <button className="theme-toggle" onClick={onToggleTheme}>
          {theme === 'light' ? 'Dark mode' : 'Light mode'}
        </button>
        <h1>CodeLlama Tutor Agent</h1>
        <p>Paste your Python code and ask a tutor question to get help with syntax, logic, and explanations.</p>
      </header>
      <ChatBox />
    </div>
  )
}

export default Home
