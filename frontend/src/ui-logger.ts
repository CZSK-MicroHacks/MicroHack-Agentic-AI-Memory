export interface UiErrorEvent {
  context: string;
  message: string;
  stack?: string;
  timestamp: string;
}

type TelemetryReporter = (event: UiErrorEvent) => void;
type UserNotifier = (message: string) => void;

interface LoggerOptions {
  notifyUser?: UserNotifier;
  reportTelemetry?: TelemetryReporter;
}

export class UiLogger {
  private notifyUser?: UserNotifier;
  private reportTelemetry?: TelemetryReporter;

  configure(options: LoggerOptions): void {
    this.notifyUser = options.notifyUser;
    this.reportTelemetry = options.reportTelemetry;
  }

  error(context: string, error: unknown, userMessage?: string): void {
    const event = this.toEvent(context, error);

    const isLocalHost =
      typeof window !== 'undefined' &&
      (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

    if (isLocalHost) {
      console.error(`[ui:${context}]`, error);
    }

    if (userMessage && this.notifyUser) {
      this.notifyUser(userMessage);
    }

    if (this.reportTelemetry) {
      try {
        this.reportTelemetry(event);
      } catch {
        // Never allow telemetry failures to affect app runtime.
      }
    }
  }

  private toEvent(context: string, error: unknown): UiErrorEvent {
    if (error instanceof Error) {
      return {
        context,
        message: error.message,
        stack: error.stack,
        timestamp: new Date().toISOString(),
      };
    }

    return {
      context,
      message: typeof error === 'string' ? error : JSON.stringify(error),
      timestamp: new Date().toISOString(),
    };
  }
}

export const uiLogger = new UiLogger();