// Window events that keep the balance in sync across the app:
// "changed" after a paid request (balance chips refresh), "payment-required"
// when the server answers 402 (the top-up dialog opens, wherever the user is).

const CHANGED = "presenton:billing-changed";
const PAYMENT_REQUIRED = "presenton:payment-required";

export function notifyBillingChanged(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(CHANGED));
}

export function notifyPaymentRequired(message: string): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent<string>(PAYMENT_REQUIRED, { detail: message }));
  }
}

export function onBillingChanged(listener: () => void): () => void {
  window.addEventListener(CHANGED, listener);
  return () => window.removeEventListener(CHANGED, listener);
}

export function onPaymentRequired(listener: (message: string) => void): () => void {
  const handler = (event: Event) => listener((event as CustomEvent<string>).detail || "");
  window.addEventListener(PAYMENT_REQUIRED, handler);
  return () => window.removeEventListener(PAYMENT_REQUIRED, handler);
}
