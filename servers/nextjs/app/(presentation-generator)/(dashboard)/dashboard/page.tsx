import React from 'react'
import DashboardPage from './components/DashboardPage'
import { getServerAuthStatus } from '@/utils/serverAuth'

const page = async () => {
  const status = await getServerAuthStatus()
  return (
    <DashboardPage isAdmin={status.role === 'admin'} />
  )
}

export default page
