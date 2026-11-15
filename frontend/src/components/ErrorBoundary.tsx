import { Component, type ErrorInfo, type ReactNode } from 'react';
import { ErrorState } from './ErrorState';

interface Props {
  children: ReactNode;
  /** Custom fallback; defaults to a full error panel. */
  fallback?: ReactNode;
  title?: string;
}

interface State {
  failed: boolean;
}

/** Prevents a render-time exception from producing a blank white screen. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('TriChurn UI error:', error, info.componentStack);
  }

  render() {
    if (this.state.failed) {
      return (
        this.props.fallback ?? (
          <ErrorState
            title={this.props.title ?? 'Something went wrong while rendering this view.'}
            onRetry={() => this.setState({ failed: false })}
          />
        )
      );
    }
    return this.props.children;
  }
}
