import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { useAuth } from './context/auth';
import AuthPage from './pages/AuthPage';
import ChatDashboard from './pages/ChatDashboard';
import AdminDocumentsPage from './pages/AdminDocumentsPage';
import { Loader2 } from 'lucide-react';
import ErrorBoundary from './components/ErrorBoundary';

function ProtectedRoute({ children, requireAdmin = false }: { children: React.ReactNode, requireAdmin?: boolean }) {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="app-container items-center justify-center" style={{ backgroundColor: 'hsl(var(--background))' }}>
        <Loader2 size={48} style={{ color: 'hsl(var(--primary))', animation: 'spin 1s linear infinite' }} />
        <style>{`@keyframes spin { 100% { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (requireAdmin && user.role !== 'admin') {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
          <Route path="/login" element={<AuthPage />} />
          <Route 
            path="/" 
            element={
              <ProtectedRoute>
                <ChatDashboard />
              </ProtectedRoute>
            } 
          />
          <Route 
            path="/admin/documents" 
            element={
              <ProtectedRoute requireAdmin={true}>
                <AdminDocumentsPage />
              </ProtectedRoute>
            } 
          />
          <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ErrorBoundary>
  );
}
