import type { ReactNode } from 'react';

export interface EmptyStateProps {
  message: string;
  /** The create action rendered under the message. */
  children: ReactNode;
}

/** Shown by every list screen when it has no rows. */
export function EmptyState({ message, children }: EmptyStateProps) {
  return (
    <div>
      <p>{message}</p>
      {children}
    </div>
  );
}
