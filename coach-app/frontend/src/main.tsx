import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom'

import App from './App'
import ExperienceBatchPage from './pages/ExperienceBatchPage'
import ExperienceHotQuestionsPage from './pages/ExperienceHotQuestionsPage'
import ExperienceLayout from './pages/ExperienceLayout'
import './styles/index.css'

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
  },
  {
    path: '/experience',
    element: <ExperienceLayout />,
    children: [
      {
        index: true,
        element: <Navigate to="batches" replace />,
      },
      {
        path: 'batches',
        children: [
          {
            index: true,
            element: <div className="p-8 text-center text-primary-600">请从左侧选择一个批次查看详情</div>,
          },
          {
            path: ':batchId',
            element: <ExperienceBatchPage />,
          },
        ],
      },
      {
        path: 'hot-questions',
        element: <ExperienceHotQuestionsPage />,
      },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
