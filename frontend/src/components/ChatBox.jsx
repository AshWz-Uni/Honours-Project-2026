import { useState } from 'react'
import API from '../api/api'

function ChatBox() {

  const [code, setCode] = useState('')
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)

  const sendMessage = async () => {

    if (!question) return

    const userMessage = {
      role: 'student',
      content: question
    }

    setMessages(prev => [...prev, userMessage])

    try {

      setLoading(true)

      const result = await API.post('/chat', {
        code,
        question
      })

      const tutorMessage = {
        role: 'tutor',
        content: result.data.response
      }

      setMessages(prev => [...prev, tutorMessage])

      setQuestion('')

    } catch (error) {

      setMessages(prev => [
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

  return (
    <div className="chat-shell">
      <section className="chat-card">
        <textarea
          className="code-input"
          rows="12"
          placeholder="Paste Python code here..."
          value={code}
          onChange={(e) => setCode(e.target.value)}
        />

        <div className="message-panel">
          {messages.length === 0 ? (
            <div className="message-empty">Chat Window</div>
          ) : (
            messages.map((msg, index) => (
              <div
                key={index}
                className={`message-row ${msg.role === 'student' ? 'user-message' : 'tutor-message'}`}
              >
                <div className="message-bubble">
                  <div className="message-role">
                    {msg.role === 'student' ? 'Student' : 'Tutor'}
                  </div>
                  <p>{msg.content}</p>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="chat-actions">
          <input
            type="text"
            className="question-input"
            placeholder="Ask the tutor a question..."
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <button
            className="send-button"
            onClick={sendMessage}
            disabled={loading}
          >
            {loading ? 'Thinking...' : 'Send'}
          </button>
        </div>
      </section>
    </div>
  )
}

export default ChatBox
