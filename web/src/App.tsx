/**
 * Placeholder app shell — verifies the full wiring (backend health,
 * auth flow, AI gateway) before a competition builds its real UI.
 * Each competition repo replaces this file with its own product UI.
 */

import { useState } from "react";
import { APP } from "./appConfig";
import { AuthProvider, useAuth } from "./lib/auth";
import { api } from "./lib/api";
import { useApi } from "./lib/useApi";
import { Badge, Button, Card, ErrorBanner, Input, Spinner, cx } from "./ui/components";

interface Health {
  status: string;
  service: string;
  version: string;
  environment: string;
  database: string;
  ai: { mode: string; backend: string; model: string };
  uptime_seconds: number;
}

function AppName() {
  return (
    <div className="app-brand">
      <span className="app-logo">▲</span>
      <span>{APP.name}</span>
    </div>
  );
}

function WiringCheck() {
  const health = useApi<Health>("/health");
  const auth = useAuth();
  const [email, setEmail] = useState("demo@example.com");
  const [password, setPassword] = useState("demo-password-123");
  const [authError, setAuthError] = useState<string | null>(null);

  const aiBadge =
    health.data?.ai.backend === "local" ? (
      <Badge tone="warning">local fallback (no API key)</Badge>
    ) : (
      <Badge tone="success">remote LLM</Badge>
    );

  return (
    <div className="page">
      <section>
        <h1>{APP.tagline}</h1>
        <p>
          Backend, database, authentication and the AI gateway are wired together. This page will
          be replaced by the competition-specific product UI.
        </p>
      </section>

      <div className="grid-2">
        <Card className="stack">
          <span className="spread">
            <h3 style={{ margin: 0 }}>Backend</h3>
            <Badge tone="success">{health.data?.status ?? "…"}</Badge>
          </span>
          {health.loading ? (
            <Spinner />
          ) : health.error ? (
            <ErrorBanner message={health.error.message} />
          ) : (
            <ul style={{ margin: 0, paddingLeft: 18, color: "var(--text-2)" }}>
              <li>
                {health.data!.service} v{health.data!.version} ({health.data!.environment})
              </li>
              <li>Database: {health.data!.database}</li>
              <li>AI: {health.data!.ai.mode} / {health.data!.ai.model} {aiBadge}</li>
            </ul>
          )}
        </Card>

        <Card className="stack">
          <span className="spread">
            <h3 style={{ margin: 0 }}>Account</h3>
            {auth.user ? <Badge tone="accent">signed in</Badge> : <Badge tone="neutral">guest</Badge>}
          </span>
          {auth.user ? (
            <>
              <p style={{ margin: 0 }}>
                <strong>{auth.user.display_name}</strong> — {auth.user.email}
              </p>
              <div>
                <Button variant="secondary" onClick={() => void auth.logout()}>
                  Log out
                </Button>
              </div>
            </>
          ) : (
            <form
              className="stack"
              onSubmit={async (e) => {
                e.preventDefault();
                setAuthError(null);
                try {
                  await auth.login(email, password);
                } catch (err) {
                  setAuthError((err as Error).message);
                }
              }}
            >
              <ErrorBanner message={authError} />
              <Input label="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
              <Input
                label="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <Button loading={auth.booting} type="submit">
                Log in (demo account)
              </Button>
            </form>
          )}
        </Card>

        <Card className="stack">
          <h3 style={{ margin: 0 }}>AI Gateway</h3>
          <p style={{ margin: 0, color: "var(--text-2)" }}>
            Send a prompt to confirm the gateway responds (deterministic fallback when no API key
            is configured).
          </p>
          <AiPing />
        </Card>
      </div>
    </div>
  );
}

function AiPing() {
  const [text, setText] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="stack">
      <ErrorBanner message={error} />
      <div className={cx("spread")}>
        <Button
          variant="secondary"
          loading={busy}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              const res = await api<{ text: string; provider: string; used_fallback: boolean }>(
                "/demo/ai-ping",
                { method: "POST", body: { prompt: "Give me one study tip." } }
              );
              setText(`${res.text}  (provider: ${res.provider})`);
            } catch (err) {
              setError((err as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          Test AI gateway
        </Button>
      </div>
      {text && (
        <p style={{ margin: 0, fontSize: 14, background: "var(--surface-2)", borderRadius: 8, padding: 12 }}>
          {text}
        </p>
      )}
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <header className="app-header">
        <AppName />
        <Badge tone="neutral">scaffold</Badge>
      </header>
      <main className="app-main">
        <WiringCheck />
      </main>
    </AuthProvider>
  );
}
