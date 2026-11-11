import {
  ApiError,
  type ChatAnswer,
  type ChatEvidence,
  type ChatServices,
} from '@/services/types';

export type ChatStreamRequest = (
  path: string,
  init: RequestInit,
) => Promise<Response>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function parseEvidence(value: unknown): ChatEvidence {
  if (!isRecord(value)) {
    throw new ApiError('The chat response did not include evidence.', 502);
  }

  const categories = [
    'figures',
    'reportingPeriods',
    'cropCycles',
    'calculationBasis',
  ] as const;
  for (const category of categories) {
    if (!Array.isArray(value[category]) || !value[category].every(isRecord)) {
      throw new ApiError('The chat response included invalid evidence.', 502);
    }
  }

  return value as unknown as ChatEvidence;
}

function parseAnswerEvent(value: unknown): ChatAnswer {
  if (!isRecord(value) || typeof value.answer !== 'string') {
    throw new ApiError(
      'The chat response included an invalid final answer.',
      502,
    );
  }

  return { answer: value.answer, evidence: parseEvidence(value.evidence) };
}

function processLine(
  line: string,
  onToken: (text: string) => void,
): ChatAnswer | undefined {
  if (!line.trim()) return undefined;

  let event: unknown;
  try {
    event = JSON.parse(line);
  } catch {
    throw new ApiError('The chat response stream was invalid.', 502);
  }

  if (!isRecord(event) || typeof event.type !== 'string') {
    throw new ApiError('The chat response stream was invalid.', 502);
  }

  if (event.type === 'token' && typeof event.text === 'string') {
    onToken(event.text);
    return undefined;
  }

  if (event.type === 'final') return parseAnswerEvent(event);

  if (
    event.type === 'error' &&
    isRecord(event.error) &&
    typeof event.error.message === 'string'
  ) {
    throw new ApiError(event.error.message, 502);
  }

  throw new ApiError('The chat response stream was invalid.', 502);
}

async function readChatStream(
  response: Response,
  onToken: (text: string) => void,
): Promise<ChatAnswer> {
  if (!response.body) {
    throw new ApiError('The chat response stream was empty.', 502);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let answer: ChatAnswer | undefined;

  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });

      let newline = buffer.indexOf('\n');
      while (newline !== -1) {
        const line = buffer.slice(0, newline);
        buffer = buffer.slice(newline + 1);
        answer = processLine(line, onToken) ?? answer;
        newline = buffer.indexOf('\n');
      }

      if (done) break;
    }

    answer = processLine(buffer, onToken) ?? answer;
  } finally {
    reader.releaseLock();
  }

  if (!answer) {
    throw new ApiError(
      'The chat response ended before the answer was complete.',
      502,
    );
  }

  return answer;
}

export function createChatHttp(requestStream: ChatStreamRequest): ChatServices {
  return {
    chat: {
      async ask(question, onToken) {
        const response = await requestStream('/chat', {
          method: 'POST',
          headers: { Accept: 'application/x-ndjson' },
          body: JSON.stringify({ question }),
        });
        return readChatStream(response, onToken);
      },
    },
  };
}
