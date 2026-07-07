import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useLogin } from "../api/hooks";
import { useAuthStore } from "../stores/auth";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const login = useLogin();
  const setTokens = useAuthStore((s) => s.setTokens);
  const navigate = useNavigate();

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    login.mutate(
      { email, password },
      {
        onSuccess: (tokens) => {
          setTokens(tokens.access_token, tokens.refresh_token);
          navigate("/");
        },
      },
    );
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="card w-full max-w-md p-8">
        <div className="mb-6 text-center">
          <div className="text-4xl">🏢</div>
          <h1 className="mt-2 text-xl font-bold">AI Software Company</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Your team of AI employees is waiting.
          </p>
        </div>
        <form onSubmit={submit} className="space-y-4">
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
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          {login.isError && (
            <p role="alert" className="text-sm text-red-500">
              {(login.error as Error).message}
            </p>
          )}
          <button type="submit" className="btn-primary w-full" disabled={login.isPending}>
            {login.isPending ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="mt-4 text-center text-sm text-slate-500">
          No account?{" "}
          <Link to="/register" className="text-accent hover:underline">
            Register
          </Link>
        </p>
      </div>
    </div>
  );
}
