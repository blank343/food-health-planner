import { Suspense } from "react";
import { BrowserRouter, NavLink, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import Login from "./auth/Login";
import { routes } from "./routes";
import { Button, Spinner } from "./ui";

function Shell() {
  const { state, logout } = useAuth();
  if (state.status === "loading") {
    return (
      <div className="login">
        <Spinner label="Anmeldung wird geprüft …" />
      </div>
    );
  }
  if (state.status === "anon") return <Login />;

  return (
    <div className="app">
      <nav className="nav" aria-label="Hauptnavigation">
        {routes.map((r) => (
          <NavLink key={r.path} to={r.path} end={r.path === "/"}>
            {r.label}
          </NavLink>
        ))}
      </nav>
      <main className="main">
        <div className="topbar">
          <small className="muted">Angemeldet als {state.person.name}</small>
          <Button variant="ghost" onClick={logout}>
            Abmelden
          </Button>
        </div>
        <Suspense fallback={<Spinner />}>
          <Routes>
            {routes.map((r) => (
              <Route key={r.path} path={r.path} element={<r.Component />} />
            ))}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Shell />
      </AuthProvider>
    </BrowserRouter>
  );
}
