import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { AuthLayout } from '@/components/AuthLayout';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuth } from '../auth/authContext';
import { toErrorMessage } from '../lib/errors';
import { useServices } from '../services/servicesContext';

export function LoginPage() {
  const services = useServices();
  const { signIn, isAuthenticated, message } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      const session = await services.auth.login({ email, password });
      signIn(session);
      navigate('/dashboard', { replace: true });
    } catch (cause) {
      setError(toErrorMessage(cause));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title="Sign in"
      description="Sign in to manage your farm."
      footer={
        <span>
          New to Agrivanta?{' '}
          <Link
            to="/register"
            className="font-medium text-primary underline-offset-4 hover:underline"
          >
            Create an account
          </Link>
        </span>
      }
    >
      {message ? (
        <p
          role="status"
          className="mb-4 rounded-md border border-border bg-muted px-3 py-2 text-sm text-muted-foreground"
        >
          {message}
        </p>
      ) : null}

      <form aria-label="Sign in" onSubmit={handleSubmit} noValidate>
        {error ? (
          <p
            role="alert"
            id="login-error"
            className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {error}
          </p>
        ) : null}

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="login-email">Email</Label>
            <Input
              id="login-email"
              name="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? 'login-error' : undefined}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="login-password">Password</Label>
            <Input
              id="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? 'login-error' : undefined}
              required
            />
          </div>

          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </Button>
        </div>
      </form>
    </AuthLayout>
  );
}
