import React from 'react'
import type { Metadata } from 'next'
import { getTranslations } from 'next-intl/server'
import SettingPage from './SettingPage'
import UserAccountSettings from './UserAccountSettings'
import { getServerAuthStatus } from '@/utils/serverAuth'
import { getSettingsView } from '@/utils/settingsAccess'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('meta')
  return {
    title: t('settingsTitle'),
    description: t('settingsDescription'),
  }
}
const page = async () => {
  const status = await getServerAuthStatus()

  return getSettingsView(status.role) === 'admin'
    ? <SettingPage />
    : <UserAccountSettings username={status.username ?? 'User'} />
}

export default page
