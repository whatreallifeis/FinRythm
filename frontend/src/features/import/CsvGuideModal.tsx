import type { ReactNode } from 'react';
import { Button } from '@/shared/ui';
import { Modal } from '@/shared/ui/Modal';

/**
 * Откуда взять CSV.
 *
 * Приложение не подключается к банку: пользователь сам выгружает операции
 * и приносит файл. Инструкция нужна, чтобы этот шаг не выглядел магией.
 */
export function CsvGuideModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Modal open={open} title="Как скачать выписку CSV" onClose={onClose}>
      <div className="space-y-4 text-sm leading-relaxed">
        <p className="text-muted">
          Разбор расходов, бюджет и цели считаются по вашим операциям. Их нужно
          один раз выгрузить из банка — пароли, SMS-коды и номера карт приложение
          не запрашивает.
        </p>

        <Section title="В приложении Т-Банка">
          <ol className="list-decimal space-y-1.5 pl-4">
            <li>Откройте нужный счёт или карту.</li>
            <li>Нажмите «Выписка» или «История операций».</li>
            <li>Выберите период — лучше последний полный месяц.</li>
            <li>Скачайте файл. Если есть выбор формата, берите CSV или Excel.</li>
          </ol>
        </Section>

        <Section title="В личном кабинете на сайте">
          <ol className="list-decimal space-y-1.5 pl-4">
            <li>Войдите в интернет-банк с компьютера.</li>
            <li>Откройте историю операций по счёту.</li>
            <li>Найдите «Скачать», «Выгрузить» или «Выписка».</li>
            <li>Сохраните файл на устройство и загрузите его сюда.</li>
          </ol>
        </Section>

        <Section title="Какие колонки нужны">
          <p className="mb-2 text-muted">
            В файле должны быть четыре колонки — порядок не важен:
          </p>
          <pre className="overflow-x-auto rounded-card bg-bg p-3 font-mono text-xs">
            date,amount,category,merchant
          </pre>
          <p className="mt-2 text-muted">
            Дата в формате ГГГГ-ММ-ДД, расход — отрицательное число, доход —
            положительное. Если банк отдал Excel, сохраните таблицу как CSV либо
            скопируйте колонки в текстовый файл.
          </p>
        </Section>

        <p className="text-xs text-muted">
          Названия пунктов меню в банке могут отличаться. Если выгрузки нет под
          рукой — нажмите «Вставить пример» на этом экране: разбор заработает на
          синтетических данных.
        </p>

        <Button fullWidth onClick={onClose}>
          Понятно
        </Button>
      </div>
    </Modal>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-1.5 font-semibold">{title}</h3>
      {children}
    </section>
  );
}
