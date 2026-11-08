import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatPage } from './ChatPage';
import { createMemorySessionStore } from '../services/sessionStore';
import { createMockServices } from '../services/mockServices';
import { ServicesContext } from '../services/servicesContext';
import type { ChatAnswer, ChatEvidence, ChatService } from '../services/types';
import { ApiError } from '../services/types';

const evidence: ChatEvidence = {
  figures: [
    { tool: 'field_profitability', path: '/data/revenue', value: 1234.5 },
  ],
  reportingPeriods: [
    {
      periodId: 'season-2026',
      startDate: '2026-01-01',
      endDate: '2026-12-31',
    },
  ],
  cropCycles: [{ id: 'cycle-8', name: 'North field wheat' }],
  calculationBasis: [
    {
      tool: 'field_profitability',
      description: 'Revenue minus posted costs.',
      recomputedByChat: false,
    },
  ],
};

async function setup(ask: ChatService['ask']) {
  const store = createMemorySessionStore();
  const services = createMockServices({ store });
  await services.auth.login({
    email: 'owner@agrivanta.test',
    password: 'password123',
  });
  services.chat = { ask };

  render(
    <ServicesContext.Provider value={services}>
      <ChatPage />
    </ServicesContext.Provider>,
  );
}

function askQuestion() {
  fireEvent.change(screen.getByRole('textbox', { name: 'Your question' }), {
    target: { value: 'What does the report say?' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Send question' }));
}

describe('ChatPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('streams an answer and displays backend evidence in a collapsed, expandable panel', async () => {
    let finishResponse: (() => void) | undefined;
    const answer = 'The report supports this answer.';
    const ask = vi.fn(
      (_question: string, onToken: (text: string) => void) =>
        new Promise<ChatAnswer>((resolve) => {
          onToken('The report ');
          finishResponse = () => {
            onToken('supports this answer.');
            resolve({ answer, evidence });
          };
        }),
    );
    await setup(ask);

    askQuestion();

    await waitFor(() =>
      expect(
        screen
          .getByLabelText('AI answer')
          .querySelector('.chat-message-content')?.textContent,
      ).toBe('The report '),
    );
    expect(screen.getByText('What does the report say?')).toBeInTheDocument();
    expect(screen.queryByText('Evidence')).not.toBeInTheDocument();

    await act(async () => finishResponse?.());

    expect(
      await screen.findByText(answer, { exact: true }),
    ).toBeInTheDocument();
    const summary = screen.getByText('Evidence');
    const details = summary.closest('details');
    expect(details).not.toHaveAttribute('open');

    fireEvent.click(summary);

    expect(details).toHaveAttribute('open');
    expect(
      screen.getByRole('heading', { name: 'Figures' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/1234\.5/)).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Reporting periods' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/season-2026/)).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Crop cycles' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/North field wheat/)).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Calculation basis' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Revenue minus posted costs/)).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByRole('textbox', { name: 'Your question' }),
      ).toBeEnabled(),
    );
  });

  it('renders the backend data-insufficient wording verbatim', async () => {
    const limitation =
      "I can't answer this because the input soil carbon is invalid or unsupported by the permitted farm query tools. No numeric result is available.";
    const ask = vi.fn(
      async (_question: string, onToken: (text: string) => void) => {
        onToken(
          "I can't answer this because the input soil carbon is invalid ",
        );
        onToken(
          'or unsupported by the permitted farm query tools. No numeric result is available.',
        );
        return { answer: limitation, evidence };
      },
    );
    await setup(ask);

    askQuestion();

    expect(
      await screen.findByText(limitation, { exact: true }),
    ).toBeInTheDocument();
  });

  it('shows backend or network failures in the conversation and allows retry', async () => {
    const ask = vi
      .fn<ChatService['ask']>()
      .mockRejectedValue(
        new ApiError('Chat service is temporarily unavailable.', 503),
      );
    await setup(ask);

    askQuestion();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Chat service is temporarily unavailable.',
    );
    fireEvent.change(screen.getByRole('textbox', { name: 'Your question' }), {
      target: { value: 'Try again' },
    });
    expect(screen.getByRole('button', { name: 'Send question' })).toBeEnabled();
    expect(screen.queryByText('Answering…')).not.toBeInTheDocument();
  });
});
