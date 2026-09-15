import { useEffect, useState } from 'react'
import Home from './pages/Home'

function App() {
  const [theme, setTheme] = useState('dark')

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  const toggleTheme = () => {
    setTheme((current) => (current === 'light' ? 'dark' : 'light'))
  }

  return <Home theme={theme} onToggleTheme={toggleTheme} />
}

export default App