import type { ReactNode } from 'react';

export interface EmptyStateProps {
  message: string;
  /** The create action rendered under the message. */
  children: ReactNode;
}

/** Shown by every list screen when it has no rows. */
export function EmptyState({ message, children }: EmptyStateProps) {
  return (
    <div className="space-y-4 rounded-xl border border-dashed bg-muted/30 px-6 py-10 text-center">
      <p>{message}</p>
      <div className="flex flex-wrap items-center justify-center gap-2">
        {children}
      </div>
    </div>
  );
}
