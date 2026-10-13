'use client';

import { Provider } from 'react-redux';
import { store } from '../store/store';
import ChatGptAuthRedirectHandler from './ChatGptAuthRedirectHandler';
import PaymentRequiredDialog from '@/components/billing/PaymentRequiredDialog';

export function Providers({ children }: { children: React.ReactNode }) {
  return <Provider store={store}>
      <ChatGptAuthRedirectHandler />
      <PaymentRequiredDialog />
      {children}
  </Provider>;
}
