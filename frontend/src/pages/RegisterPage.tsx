import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useLogin, useRegister } from "../api/hooks";
import { useAuthStore } from "../stores/auth";

export default function RegisterPage() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const register = useRegister();
  const login = useLogin();
  const setTokens = useAuthStore((s) => s.setTokens);
  const navigate = useNavigate();

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    register.mutate(
      { email, password, full_name: fullName },
      {
        onSuccess: () =>
          login.mutate(
            { email, password },
            {
              onSuccess: (tokens) => {
                setTokens(tokens.access_token, tokens.refresh_token);
                navigate("/");
              },
            },
          ),
      },
    );
  };

  const busy = register.isPending || login.isPending;
  const error = (register.error ?? login.error) as Error | null;

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="card w-full max-w-md p-8">
        <div className="mb-6 text-center">
          <div className="text-4xl">🏢</div>
          <h1 className="mt-2 text-xl font-bold">Create your account</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Hire a 12-agent software company in seconds.
          </p>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label htmlFor="fullName" className="mb-1 block text-sm font-medium">
              Full name
            </label>
            <input
              id="fullName"
              required
              className="input"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              autoComplete="name"
            />
          </div>
          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium">
              Password <span className="text-xs text-slate-400">(min 8 characters)</span>
            </label>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
            />
          </div>
          {error && (
            <p role="alert" className="text-sm text-red-500">
              {error.message}
            </p>
          )}
          <button type="submit" className="btn-primary w-full" disabled={busy}>
            {busy ? "Creating…" : "Create account"}
          </button>
        </form>
        <p className="mt-4 text-center text-sm text-slate-500">
          Already registered?{" "}
          <Link to="/login" className="text-accent hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
