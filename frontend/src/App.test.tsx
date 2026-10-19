import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { App } from './App';

describe('App', () => {
  it('renders the scaffold heading and copy', () => {
    render(<App />);

    expect(
      screen.getByRole('heading', { level: 1, name: 'Agrivanta frontend' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Vite + React 18 + TypeScript scaffold is running.'),
    ).toBeInTheDocument();
  });
});
