import { useState } from 'react'
import API from '../api/api'

const LANGUAGE_OPTIONS = [
  { value: 'auto', label: 'Auto-detect' },
  { value: 'python', label: 'Python' },
  { value: 'javascript', label: 'JavaScript' }
]

const LANGUAGE_LABELS = { python: 'Python', javascript: 'JavaScript' }

const PLACEHOLDERS = {
  auto: 'Paste your Python or JavaScript code here...',
  python: 'Paste Python code here...',
  javascript: 'Paste JavaScript code here...'
}

function ChatBox() {
  const [code, setCode] = useState('')
  // 'auto' lets the backend detect the language from the code.
  const [language, setLanguage] = useState('auto')
  // Language the tutor actually used on the last turn (chosen or detected).
  const [activeLanguage, setActiveLanguage] = useState(null)
  // Keeps the Socratic dialogue in one backend conversation across turns.
  const [conversationId, setConversationId] = useState(null)
  const [concluded, setConcluded] = useState(false)
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)

  const sendMessage = async () => {
    const trimmedQuestion = question.trim()

    if (!trimmedQuestion || loading) return

    const userMessage = {
      role: 'student',
      content: trimmedQuestion
    }

    setMessages((prev) => [...prev, userMessage])
    setQuestion('')

    try {
      setLoading(true)

      const result = await API.post('/chat', {
        code,
        question: trimmedQuestion,
        language,
        conversation_id: conversationId
      })

      setConversationId(result.data.conversation_id)
      setActiveLanguage(result.data.language ?? null)
      setConcluded(Boolean(result.data.concluded))

      const tutorMessage = {
        role: 'tutor',
        content: result.data.response
      }

      setMessages((prev) => [...prev, tutorMessage])
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'tutor',
          content: 'Error connecting to backend.'
        }
      ])
    } finally {
      setLoading(false)
    }
  }

  /* Starts a fresh tutoring dialogue (drops the backend conversation state). */
  const newConversation = async () => {
    if (conversationId) {
      try {
        await API.delete(`/chat/${conversationId}`)
      } catch (error) {
        // The conversation may already be gone; starting over is still fine.
      }
    }
    setConversationId(null)
    setActiveLanguage(null)
    setConcluded(false)
    setMessages([])
  }

  /* Copies the complete conversation Tutor responses */
  const copyConversation = async () => {
    if (!code.trim() && messages.length === 0) return

    const conversation = []

    if (code.trim()) {
      conversation.push(
        '=== Student Code ===',
        code.trim(),
        ''
      )
    }

    if (messages.length > 0) {
      conversation.push('=== Conversation ===', '')

      messages.forEach((message) => {
        const speaker =
          message.role === 'student' ? 'Student' : 'Tutor'

        conversation.push(
          `${speaker}:`,
          message.content.trim(),
          ''
        )
      })
    }

    const conversationText = conversation.join('\n').trim()

    try {
      await navigator.clipboard.writeText(conversationText)

      setCopied(true)

      // Reset the button text after a short delay.
      setTimeout(() => {
        setCopied(false)
      }, 2000)
    } catch (error) {
      console.error('Failed to copy conversation:', error)
    }
  }

  const handleQuestionKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="chat-shell">
      <section className="chat-card">

        {/* Code input */}
        <div className="input-section">
          <div className="code-header">
            <label htmlFor="code-input" className="input-label">
              Your Code
            </label>

            <div className="language-controls">
              <label htmlFor="language-select" className="input-label">
                Language
              </label>
              <select
                id="language-select"
                className="language-select"
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
              >
                {LANGUAGE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              {language === 'auto' && activeLanguage && (
                <span className="language-badge">
                  Detected: {LANGUAGE_LABELS[activeLanguage] ?? activeLanguage}
                </span>
              )}
            </div>
          </div>

          <textarea
            id="code-input"
            className="code-input"
            rows="12"
            placeholder={PLACEHOLDERS[language]}
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </div>

        {/* Conversation header and copy button */}
        <div className="conversation-header">
          <h2>Conversation</h2>

          <button
            className="copy-button"
            onClick={newConversation}
            disabled={!conversationId && messages.length === 0}
            type="button"
            aria-label="Discard this conversation and start a new one"
          >
            New conversation
          </button>

          <button
            className="copy-button"
            onClick={copyConversation}
            disabled={!code.trim() && messages.length === 0}
            type="button"
            aria-label="Copy the entire conversation including code"
          >
            {copied ? 'Copied!' : 'Copy conversation'}
          </button>
        </div>

        {/* Conversation */}
        <div className="message-panel">
          {messages.length === 0 ? (
            <div className="message-empty">
              Chat Window
            </div>
          ) : (
            messages.map((msg, index) => (
              <div
                key={index}
                className={`message-row ${
                  msg.role === 'student'
                    ? 'user-message'
                    : 'tutor-message'
                }`}
              >
                <div className="message-bubble">
                  <div className="message-role">
                    {msg.role === 'student'
                      ? 'Student'
                      : 'Tutor'}
                  </div>

                  <p>{msg.content}</p>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Question input */}
        <div className="chat-actions">
          <label
            htmlFor="question-input"
            className="input-label"
          >
            Ask the tutor
          </label>

          <textarea
            id="question-input"
            className="question-input"
            rows="2"
            placeholder="Ask the tutor a question..."
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleQuestionKeyDown}
            disabled={loading || concluded}
            aria-label="Ask the tutor a question"
          />

          <div className="input-hint">
            Press Enter to send · Shift + Enter for a new line
          </div>

          {concluded && (
            <div className="input-hint">
              This tutoring dialogue has concluded. Start a new conversation to work on another problem.
            </div>
          )}

          {loading && (
            <div className="thinking-indicator">
              Tutor is thinking...
            </div>
          )}
        </div>

      </section>
    </div>
  )
}

export default ChatBox