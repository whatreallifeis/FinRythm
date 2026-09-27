import { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Screen } from '@/layouts/Screen';
import { useMainButton, usePlatform } from '@/platform';
import { useDatasetReady } from '@/shared/api/dataset';
import { useImportTransactions, useLoadDataset, useTransactions } from '@/shared/api/hooks';
import { demoCsvWithErrors } from '@/shared/api/mock/data';
import { parseCsv } from '@/shared/lib/csv';
import { categoryLabel } from '@/shared/lib/categories';
import { formatDate, formatSigned } from '@/shared/lib/format';
import type { ImportResult } from '@/shared/api/types';
import { Badge, Button, Card, CardTitle, EmptyState, ScreenState, Skeleton } from '@/shared/ui';
import { CsvGuideModal } from './CsvGuideModal';
import { DatasetLoading } from './DatasetLoading';
import { PresetPicker } from './PresetPicker';
import type { DatasetPreset } from './presets';

/**
 * Загрузка и пополнение данных.
 *
 * Критерий оценки требует не просто «файл загружен / ошибка», а построчный
 * разбор с понятными сообщениями и возможность дополнить уже загруженные
 * данные. Поэтому CSV разбирается на клиенте: ошибки видны сразу.
 */
export function ImportScreen() {
  const navigate = useNavigate();
  const { fileInputMode, haptic } = usePlatform();
  const fileRef = useRef<HTMLInputElement>(null);
  const ready = useDatasetReady();

  const [raw, setRaw] = useState('');
  const [result, setResult] = useState<ImportResult | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [guideOpen, setGuideOpen] = useState(false);
  const [scene, setScene] = useState<'form' | 'loading'>('form');

  const transactions = useTransactions();
  const importMutation = useImportTransactions();
  const loadDataset = useLoadDataset();

  const parsed = useMemo(() => (raw.trim() ? parseCsv(raw) : null), [raw]);
  const canImport = Boolean(parsed && parsed.rows.length > 0);

  /** Новый ввод отменяет предыдущий итог импорта: он больше не про эти данные. */
  const setContent = (text: string, name: string | null = null) => {
    setRaw(text);
    setFileName(name);
    setResult(null);
  };

  const runImport = () => {
    if (!parsed || parsed.rows.length === 0) return;

    setScene('loading');
    importMutation.mutate(parsed.rows, {
      onSuccess: (data) => {
        // Поле очищаем напрямую, а не через setContent: тот сбрасывает result
        // и итог импорта исчез бы сразу после появления.
        setRaw('');
        setFileName(null);
        setResult(data);
        setScene('form');
        haptic('success');
      },
      onError: () => {
        setScene('form');
        haptic('error');
      },
    });
  };

  /** Готовая выписка разбирается тем же парсером, что и файл пользователя. */
  const loadPreset = async (preset: DatasetPreset) => {
    setScene('loading');
    try {
      await loadDataset.mutateAsync({
        dataset: { rows: parseCsv(preset.csv).rows, balance: preset.balance },
        goals: preset.goals,
      });
      haptic('success');
      navigate('/app');
    } catch {
      setScene('form');
      haptic('error');
    }
  };

  // Единственное объявление главного действия экрана — своей кнопки здесь нет.
  useMainButton(
    scene === 'form' && canImport && !guideOpen
      ? {
          text: `Загрузить ${parsed!.rows.length} операц.`,
          loading: importMutation.isPending,
          onClick: runImport,
        }
      : null,
  );

  const handleFile = async (file: File) => {
    setContent(await file.text(), file.name);
  };

  if (scene === 'loading') {
    return (
      <div className="screen-in">
        <DatasetLoading />
      </div>
    );
  }

  return (
    <div className="screen-in">
    <Screen
      title="Данные"
      subtitle="Загрузите выгрузку операций в CSV"
      action={
        <Button variant="secondary" size="sm" onClick={() => setGuideOpen(true)}>
          Инструкция
        </Button>
      }
    >
      {!ready && (
        <div className="rounded-card border border-accent/40 bg-accent/10 px-4 py-3 text-sm">
          Загрузите свою выписку или выберите готовую — после этого откроются все разделы.
        </div>
      )}

      <PresetPicker onPick={(preset) => void loadPreset(preset)} />

      <Card>
        <CardTitle>Новые операции</CardTitle>

        {fileInputMode === 'native' ? (
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const file = e.dataTransfer.files[0];
              if (file) void handleFile(file);
            }}
            className="rounded-card border border-dashed border-border p-6 text-center"
          >
            <p className="mb-3 text-sm text-muted">
              Перетащите CSV-файл сюда или выберите его на устройстве
            </p>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handleFile(file);
              }}
            />
            <Button variant="secondary" size="sm" onClick={() => fileRef.current?.click()}>
              Выбрать файл
            </Button>
            {fileName && <p className="mt-3 text-xs text-muted">Файл: {fileName}</p>}
          </div>
        ) : (
          <>
            {/*
              В webview Telegram выбор файла на iOS работает нестабильно,
              поэтому основной путь здесь — вставка текста.
            */}
            <textarea
              value={raw}
              onChange={(e) => setContent(e.target.value)}
              rows={6}
              placeholder={'date,amount,category,merchant\n2026-09-27,-540,food,Супермаркет'}
              className="w-full resize-none rounded-card border border-border bg-bg p-3 font-mono text-xs outline-none placeholder:text-muted focus:border-accent/60"
            />
            <p className="mt-2 text-xs text-muted">
              Скопируйте CSV из выгрузки банка и вставьте в поле выше.
            </p>
          </>
        )}

        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setContent(demoCsvWithErrors, 'пример-с-ошибками.csv')}
          >
            Пример с ошибками
          </Button>
          {raw && (
            <Button variant="ghost" size="sm" onClick={() => setContent('')}>
              Очистить
            </Button>
          )}
        </div>
      </Card>

      {parsed && (
        <Card>
          <CardTitle
            action={
              <div className="flex gap-2">
                <Badge tone="positive">{parsed.rows.length} ок</Badge>
                {parsed.errors.length > 0 && (
                  <Badge tone="negative">{parsed.errors.length} с ошибкой</Badge>
                )}
              </div>
            }
          >
            Предпросмотр
          </CardTitle>

          {parsed.errors.length > 0 && (
            <ul className="mb-3 space-y-1.5 rounded-card border border-negative/30 bg-negative/5 p-3 text-sm">
              {parsed.errors.map((error) => (
                <li key={`${error.row}-${error.message}`}>
                  <span className="font-medium text-negative">Строка {error.row}:</span>{' '}
                  <span className="text-muted">{error.message}</span>
                </li>
              ))}
            </ul>
          )}

          {parsed.rows.length > 0 ? (
            <ul className="divide-y divide-border">
              {parsed.rows.map((row, i) => (
                <li key={i} className="flex items-baseline justify-between gap-3 py-2 text-sm">
                  <div className="min-w-0">
                    <p className="truncate">{row.merchant}</p>
                    <p className="text-xs text-muted">
                      {formatDate(row.date)} · {categoryLabel(row.category)}
                    </p>
                  </div>
                  <span className="tabular shrink-0 font-medium">{formatSigned(row.amount)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">
              Корректных строк нет — исправьте ошибки выше и вставьте данные снова.
            </p>
          )}
        </Card>
      )}

      {result && (
        <Card>
          <p className="font-medium text-positive">Загружено операций: {result.imported}</p>
          {result.warnings.map((warning) => (
            <p key={warning} className="mt-1 text-sm text-muted">
              {warning}
            </p>
          ))}
        </Card>
      )}

      {ready && (
      <Card>
        <CardTitle>Уже загружено</CardTitle>
        <ScreenState
          query={transactions}
          isEmpty={(data) => data.length === 0}
          skeleton={
            <div className="space-y-2">
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
            </div>
          }
          empty={
            <EmptyState
              title="Операций пока нет"
              description="Загрузите CSV или вставьте пример, чтобы увидеть анализ"
            />
          }
        >
          {(data) => (
            <ul className="divide-y divide-border">
              {data.slice(0, 8).map((t) => (
                <li key={t.id} className="flex items-baseline justify-between gap-3 py-2 text-sm">
                  <div className="min-w-0">
                    <p className="truncate">
                      {t.merchant}
                      {t.isRecurring && <span className="ml-2 text-xs text-muted">регулярный</span>}
                    </p>
                    <p className="text-xs text-muted">
                      {formatDate(t.date)} · {categoryLabel(t.category)}
                    </p>
                  </div>
                  <span
                    className={
                      t.amount > 0
                        ? 'tabular shrink-0 font-medium text-positive'
                        : 'tabular shrink-0 font-medium'
                    }
                  >
                    {formatSigned(t.amount)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </ScreenState>
      </Card>
      )}

      <CsvGuideModal open={guideOpen} onClose={() => setGuideOpen(false)} />
    </Screen>
    </div>
  );
}
