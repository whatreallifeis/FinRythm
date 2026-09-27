import { Navigate, Outlet, Route, Routes, useNavigate } from 'react-router-dom';
import { AppLayout } from '@/layouts/AppLayout';
import { WelcomeScreen } from '@/features/auth/WelcomeScreen';
import { useAuthStatus } from '@/features/auth/session';
import { useAuth } from '@/features/auth/useAuth';
import { DashboardScreen } from '@/features/dashboard/DashboardScreen';
import { AssistantScreen } from '@/features/assistant/AssistantScreen';
import { ScenarioDialogRoute } from '@/features/assistant/ScenarioDialog';
import { HistoryScreen } from '@/features/assistant/HistoryScreen';
import { HistoryEntryScreen } from '@/features/assistant/HistoryEntryScreen';
import { GoalsScreen } from '@/features/goals/GoalsScreen';
import { ImportScreen } from '@/features/import/ImportScreen';
import { ErrorState } from '@/shared/ui';
import { Splash } from './Splash';

export function App() {
  // Единственный вызов бутстрапа сессии на всё приложение.
  useAuth();

  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />

      <Route element={<RequireSession />}>
        <Route path="/app" element={<AppLayout />}>
          <Route index element={<DashboardScreen />} />
          <Route path="assistant" element={<AssistantScreen />} />
          {/* Статические сегменты объявлены до :scenarioId, чтобы маршруты
              истории читались однозначно. */}
          <Route path="assistant/history" element={<HistoryScreen />} />
          <Route path="assistant/history/:entryId" element={<HistoryEntryScreen />} />
          <Route path="assistant/:scenarioId" element={<ScenarioDialogRoute />} />
          <Route path="goals" element={<GoalsScreen />} />
          <Route path="import" element={<ImportScreen />} />
        </Route>
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

/** В Telegram вход автоматический, поэтому приветственный экран пропускаем. */
function RootRedirect() {
  const status = useAuthStatus();

  if (status === 'restoring' || status === 'authenticating') return <Splash />;
  if (status === 'authenticated') return <Navigate to="/app" replace />;
  return <WelcomeScreen />;
}

function RequireSession() {
  const status = useAuthStatus();

  if (status === 'restoring' || status === 'authenticating') return <Splash />;
  if (status !== 'authenticated') return <Navigate to="/" replace />;
  return <Outlet />;
}

function NotFound() {
  const navigate = useNavigate();

  return (
    <div className="mx-auto max-w-[480px] px-4 py-10">
      <ErrorState
        message="Такой страницы нет"
        retryLabel="На главную"
        onRetry={() => navigate('/', { replace: true })}
      />
    </div>
  );
}
