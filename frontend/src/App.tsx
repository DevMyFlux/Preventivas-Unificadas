import { AuthProvider, useAuth } from './app/AuthContext';
import Shell from './app/Shell';
import LoginPage from './features/auth/LoginPage';
import { ToastProvider } from './shared/ui/Toast';
import { Spinner } from './shared/ui/ui';

function Gate() {
  const { user, loading } = useAuth();
  if (loading) {
    return <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}><Spinner label="Verificando sessão…" /></div>;
  }
  return user ? <Shell /> : <LoginPage />;
}

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <Gate />
      </AuthProvider>
    </ToastProvider>
  );
}
