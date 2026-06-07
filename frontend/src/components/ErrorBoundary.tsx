import { Component, type ErrorInfo, type ReactNode } from 'react';

interface State {
  hasError: boolean;
}

export default class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled UI error', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="app-container items-center justify-center p-4">
          <section className="glass-panel p-8 text-center" role="alert">
            <h1 className="text-xl font-bold mb-4">Giao diện gặp lỗi</h1>
            <p className="text-muted mb-4">Hãy tải lại trang để khôi phục phiên làm việc.</p>
            <button className="btn btn-primary" onClick={() => window.location.reload()}>
              Tải lại trang
            </button>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}
