import { useRef, useState, type FormEvent } from 'react';
import { useServices } from '../services/servicesContext';
import type { ChatEvidence, ChatEvidenceItem } from '../services/types';
import './ChatPage.css';

type Message = {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  loading?: boolean;
  evidence?: ChatEvidence;
  error?: string;
};

const EVIDENCE_SECTIONS = [
  { key: 'figures', title: 'Figures' },
  { key: 'reportingPeriods', title: 'Reporting periods' },
  { key: 'cropCycles', title: 'Crop cycles' },
  { key: 'calculationBasis', title: 'Calculation basis' },
] as const;

function EvidencePanel({ evidence }: { evidence: ChatEvidence }) {
  return (
    <details className="chat-evidence">
      <summary>Evidence</summary>
      {EVIDENCE_SECTIONS.map(({ key, title }) => {
        const items = evidence[key] as ChatEvidenceItem[];
        return (
          <section key={key} aria-label={title}>
            <h3>{title}</h3>
            {items.length > 0 ? (
              <ul>
                {items.map((item, index) => (
                  <li key={`${key}-${index}`}>
                    <pre>{JSON.stringify(item, null, 2)}</pre>
                  </li>
                ))}
              </ul>
            ) : (
              <p>None returned.</p>
            )}
          </section>
        );
      })}
    </details>
  );
}

export function ChatPage() {
  const { chat } = useServices();
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [pending, setPending] = useState(false);
  const messageId = useRef(0);

  async function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submittedQuestion = question.trim();
    if (!submittedQuestion || pending) return;

    const userMessageId = ++messageId.current;
    const assistantMessageId = ++messageId.current;
    setMessages((current) => [
      ...current,
      { id: userMessageId, role: 'user', content: submittedQuestion },
      {
        id: assistantMessageId,
        role: 'assistant',
        content: '',
        loading: true,
      },
    ]);
    setQuestion('');
    setPending(true);

    try {
      const result = await chat.ask(submittedQuestion, (text) => {
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantMessageId
              ? { ...message, content: message.content + text }
              : message,
          ),
        );
      });
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                content: result.answer,
                loading: false,
                evidence: result.evidence,
              }
            : message,
        ),
      );
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : 'The chat response could not be loaded.';
      setMessages((current) =>
        current.map((item) =>
          item.id === assistantMessageId
            ? { ...item, loading: false, error: message }
            : item,
        ),
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="chat-page">
      <h1>AI analyst</h1>
      <p>Ask a question about your farm records.</p>

      <section
        className="chat-conversation"
        aria-label="Conversation"
        aria-live="polite"
        aria-busy={pending}
      >
        {messages.length === 0 ? (
          <p>Ask a question to start a conversation.</p>
        ) : (
          messages.map((message) => (
            <article
              className={`chat-message chat-message-${message.role}`}
              key={message.id}
              aria-label={
                message.role === 'user' ? 'Your question' : 'AI answer'
              }
            >
              <h2>{message.role === 'user' ? 'You' : 'AI analyst'}</h2>
              {message.content && (
                <p className="chat-message-content">{message.content}</p>
              )}
              {message.role === 'assistant' &&
                message.loading &&
                !message.content && (
                  <p role="status">Waiting for the answer…</p>
                )}
              {message.error && <p role="alert">{message.error}</p>}
              {message.evidence && (
                <EvidencePanel evidence={message.evidence} />
              )}
            </article>
          ))
        )}
      </section>

      <form className="chat-question-form" onSubmit={submitQuestion}>
        <label htmlFor="chat-question">Your question</label>
        <textarea
          id="chat-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          rows={3}
          maxLength={4000}
          disabled={pending}
        />
        <button type="submit" disabled={pending || !question.trim()}>
          {pending ? 'Answering…' : 'Send question'}
        </button>
      </form>
    </div>
  );
}
