import { describe, expect, it, vi } from 'vitest';
import { createMemorySessionStore } from '@/services/sessionStore';
import { createHttpServices } from '@/services/httpServices';
import type { ChatEvidence } from '@/services/types';

describe('chat HTTP service', () => {
  it('sends an authenticated question and delivers streamed backend tokens and evidence', async () => {
    const evidence: ChatEvidence = {
      figures: [
        { tool: 'inventory_position', path: '/data/quantity', value: 25 },
      ],
      reportingPeriods: [],
      cropCycles: [],
      calculationBasis: [
        {
          tool: 'inventory_position',
          description: 'Backend calculation basis.',
          recomputedByChat: false,
        },
      ],
      toolResults: [],
    };
    const fetchFn = vi.fn(async (input: string, init?: RequestInit) => {
      void input;
      void init;
      return new Response(
        [
          JSON.stringify({ type: 'token', text: 'Farm ' }),
          JSON.stringify({ type: 'token', text: 'answer.' }),
          JSON.stringify({
            type: 'final',
            answer: 'Farm answer.',
            evidence,
          }),
          '',
        ].join('\n'),
        { status: 200 },
      );
    });
    const store = createMemorySessionStore();
    store.save({
      token: 'test-session-token',
      user: { id: 'owner-1', email: 'owner@example.test', role: 'owner' },
    });
    const services = createHttpServices({
      baseUrl: 'https://api.example.test/api',
      store,
      fetchFn,
    });
    const tokens: string[] = [];

    const result = await services.chat.ask('How much inventory?', (text) =>
      tokens.push(text),
    );

    expect(fetchFn).toHaveBeenCalledOnce();
    expect(fetchFn).toHaveBeenCalledWith(
      'https://api.example.test/api/chat',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: 'Bearer test-session-token',
          Accept: 'application/x-ndjson',
        }),
        body: JSON.stringify({ question: 'How much inventory?' }),
      }),
    );
    expect(tokens).toEqual(['Farm ', 'answer.']);
    expect(result).toEqual({ answer: 'Farm answer.', evidence });
  });
});
