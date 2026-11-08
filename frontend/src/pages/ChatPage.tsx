import { useRef, useState, type FormEvent } from 'react';
import { cn } from '@/lib/utils';
import { Button } from '../components/ui/button';
import { useServices } from '../services/servicesContext';
import type { ChatEvidence, ChatEvidenceItem } from '../services/types';

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
    <details className="mt-4 border-t pt-3">
      <summary className="cursor-pointer text-sm font-medium text-foreground">
        Evidence
      </summary>
      <div className="mt-4 space-y-5">
        {EVIDENCE_SECTIONS.map(({ key, title }) => {
          const items = evidence[key] as ChatEvidenceItem[];
          return (
            <section key={key} aria-label={title} className="space-y-2">
              <h3>{title}</h3>
              {items.length > 0 ? (
                <ul className="space-y-2">
                  {items.map((item, index) => (
                    <li
                      key={`${key}-${index}`}
                      className="overflow-x-auto rounded-lg border bg-muted/40 p-3"
                    >
                      <pre className="text-xs text-foreground">
                        {JSON.stringify(item, null, 2)}
                      </pre>
                    </li>
                  ))}
                </ul>
              ) : (
                <p>None returned.</p>
              )}
            </section>
          );
        })}
      </div>
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
    <div className="mx-auto w-full max-w-3xl space-y-6">
      <div className="space-y-1">
        <h1>AI analyst</h1>
        <p>Ask a question about your farm records.</p>
      </div>

      <section
        className="min-h-64 space-y-4 rounded-xl border bg-card p-4 text-card-foreground shadow-sm sm:p-6"
        aria-label="Conversation"
        aria-live="polite"
        aria-busy={pending}
      >
        {messages.length === 0 ? (
          <p>Ask a question to start a conversation.</p>
        ) : (
          messages.map((message) => (
            <article
              className={cn(
                'rounded-xl border p-4',
                message.role === 'user'
                  ? 'border-transparent bg-secondary text-secondary-foreground'
                  : 'bg-background',
              )}
              key={message.id}
              aria-label={
                message.role === 'user' ? 'Your question' : 'AI answer'
              }
            >
              <h2 className="text-sm">
                {message.role === 'user' ? 'You' : 'AI analyst'}
              </h2>
              {message.content && (
                <p className="chat-message-content mt-2 whitespace-pre-wrap text-foreground">
                  {message.content}
                </p>
              )}
              {message.role === 'assistant' &&
                message.loading &&
                !message.content && (
                  <p role="status" className="mt-2">
                    Waiting for the answer…
                  </p>
                )}
              {message.error && (
                <p role="alert" className="mt-2">
                  {message.error}
                </p>
              )}
              {message.evidence && (
                <EvidencePanel evidence={message.evidence} />
              )}
            </article>
          ))
        )}
      </section>

      <form className="page-form" onSubmit={submitQuestion}>
        <div>
          <label htmlFor="chat-question">Your question</label>
          <textarea
            id="chat-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={3}
            maxLength={4000}
            disabled={pending}
          />
        </div>
        <Button type="submit" disabled={pending || !question.trim()}>
          {pending ? 'Answering…' : 'Send question'}
        </Button>
      </form>
    </div>
  );
}
