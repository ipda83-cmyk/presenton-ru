"use client";

import React from "react";
import { useTranslations } from "next-intl";

interface SlideErrorBoundaryProps {
  children: React.ReactNode;
  label?: string;
  resetKey?: unknown;
}

interface SlideErrorBoundaryState {
  hasError: boolean;
  errorMessage: string;
}

function SlideErrorFallback({
  label,
  errorMessage,
}: {
  label?: string;
  errorMessage: string;
}) {
  const t = useTranslations("editor");
  return (
    <div className="aspect-video w-full h-full bg-red-50 text-red-700 flex flex-col items-start justify-start p-4 space-y-2 rounded-md border border-red-200">
      <div className="text-sm font-semibold">
        {label ? t("render.renderErrorLabel", { label }) : t("render.renderError")}
      </div>
      <pre className="text-xs whitespace-pre-wrap break-words max-h-full overflow-auto bg-red-100 rounded-md p-2 border border-red-200">
        {errorMessage}
      </pre>
    </div>
  );
}

export class SlideErrorBoundary extends React.Component<
  SlideErrorBoundaryProps,
  SlideErrorBoundaryState
> {
  constructor(props: SlideErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, errorMessage: "" };
  }

  static getDerivedStateFromError(error: unknown): SlideErrorBoundaryState {
    return {
      hasError: true,
      errorMessage: error instanceof Error ? error.message : String(error),
    };
  }

  componentDidCatch(error: unknown) {
    // Optionally log to an error reporting service
    console.error("Slide render error:", error);
  }

  componentDidUpdate(prevProps: SlideErrorBoundaryProps) {
    if (
      this.state.hasError &&
      !Object.is(prevProps.resetKey, this.props.resetKey)
    ) {
      this.setState({ hasError: false, errorMessage: "" });
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <SlideErrorFallback
          label={this.props.label}
          errorMessage={this.state.errorMessage}
        />
      );
    }
    return this.props.children;
  }
}

export default SlideErrorBoundary;
