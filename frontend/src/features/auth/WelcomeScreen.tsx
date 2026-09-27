import { usePlatform } from '@/platform';
import { Button, Card } from '@/shared/ui';
import { Disclaimer } from '@/features/explain/Disclaimer';
import { MotionStage } from '@/shared/motion/MotionStage';
import { useAuthStatus } from './session';
import { useAuth } from './useAuth';

/** Ссылка на бота: в нём сайт открывается как Mini App. */
const BOT_URL = 'https://t.me/finrythmbot';

/**
 * Первый экран в браузере.
 *
 * Демо-вход без регистрации здесь принципиален: проверяющий должен увидеть
 * работающий продукт, не имея аккаунта. В Telegram этот экран не показывается —
 * там вход происходит автоматически по initData.
 */
export function WelcomeScreen() {
  const { theme, setTheme, openExternal } = usePlatform();
  const status = useAuthStatus();
  const { signInDemo } = useAuth();

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-[480px] flex-col justify-center px-4 py-10">
      <MotionStage>
        <div className="mb-8">
          <h1 className="mb-2 text-2xl font-semibold">Финансовый помощник</h1>
          <p className="text-muted">
            Разбирает ваши доходы и расходы, считает бюджет до конца месяца и показывает, на чём
            основан каждый вывод.
          </p>
        </div>

        <div className="space-y-3">
          <Button
            size="lg"
            fullWidth
            loading={status === 'authenticating'}
            onClick={() => void signInDemo()}
          >
            Открыть сервис
          </Button>

          <Button size="lg" variant="secondary" fullWidth onClick={() => openExternal(BOT_URL)}>
            Открыть в Telegram
          </Button>
        </div>

        <Card className="mt-6">
          <p className="text-sm text-muted">
          Демо работает на синтетических данных. На экране «Данные» выберите одну из готовых
          выписок — появятся обзор, помощник и цели. Карты и пароли приложение не запрашивает и не хранит.
          </p>
        </Card>

        {/* Переключатель темы нужен, чтобы проверять оформление в обеих схемах. */}
        <button
          type="button"
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          className="mx-auto mt-6 block text-xs text-muted underline underline-offset-2"
        >
          {theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
        </button>

        <Disclaimer />
      </MotionStage>
    </div>
  );
}
