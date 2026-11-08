import type { ReactNode } from 'react';
import { Sprout } from 'lucide-react';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
} from '@/components/ui/card';

export interface AuthLayoutProps {
  title: string;
  description: string;
  children: ReactNode;
  footer?: ReactNode;
}

/** Centered card layout shared by the sign-in and registration screens. */
export function AuthLayout({
  title,
  description,
  children,
  footer,
}: AuthLayoutProps) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-background via-background to-secondary px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center justify-center gap-2">
          <span className="flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Sprout className="size-6" aria-hidden="true" />
          </span>
          <span className="text-xl font-semibold tracking-tight">
            Agrivanta
          </span>
        </div>

        <Card>
          <CardHeader>
            <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
            <CardDescription>{description}</CardDescription>
          </CardHeader>
          <CardContent>{children}</CardContent>
          {footer ? (
            <CardFooter className="justify-center text-sm text-muted-foreground">
              {footer}
            </CardFooter>
          ) : null}
        </Card>
      </div>
    </main>
  );
}
