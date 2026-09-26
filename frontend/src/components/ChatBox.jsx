import { useState } from 'react'
import API from '../api/api'

function ChatBox() {
  const [code, setCode] = useState('')
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
        question: trimmedQuestion
      })

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
          <label htmlFor="code-input" className="input-label">
            Your Code
          </label>

          <textarea
            id="code-input"
            className="code-input"
            rows="12"
            placeholder="Paste Python code here..."
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </div>

        {/* Conversation header and copy button */}
        <div className="conversation-header">
          <h2>Conversation</h2>

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
            disabled={loading}
            aria-label="Ask the tutor a question"
          />

          <div className="input-hint">
            Press Enter to send · Shift + Enter for a new line
          </div>

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