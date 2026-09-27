import { csvRowSchema } from '../api/schemas';
import type { CategoryId, ImportRowError } from '../api/types';

/**
 * Разбор CSV на клиенте.
 *
 * Делаем это на фронте намеренно: пользователь видит ошибки построчно сразу,
 * без обращения к серверу. Парсер минимальный — поддерживает кавычки и
 * запятую как разделитель, чего достаточно для банковских выгрузок.
 */

export interface ParsedRow {
  date: string;
  amount: number;
  category: CategoryId;
  merchant: string;
}

export interface ParseResult {
  rows: ParsedRow[];
  errors: ImportRowError[];
}

const REQUIRED_COLUMNS = ['date', 'amount', 'category', 'merchant'] as const;

function splitLine(line: string): string[] {
  const cells: string[] = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (char === '"') {
      // Две кавычки подряд внутри поля — это экранированная кавычка.
      if (inQuotes && line[i + 1] === '"') {
        current += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === ',' && !inQuotes) {
      cells.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }
  cells.push(current.trim());
  return cells;
}

export function parseCsv(text: string): ParseResult {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);

  if (lines.length === 0) {
    return { rows: [], errors: [{ row: 0, message: 'Файл пустой' }] };
  }

  const header = splitLine(lines[0]).map((h) => h.toLowerCase());
  const missing = REQUIRED_COLUMNS.filter((c) => !header.includes(c));
  if (missing.length > 0) {
    return {
      rows: [],
      errors: [
        {
          row: 1,
          message: `В заголовке не хватает колонок: ${missing.join(', ')}. Ожидается: ${REQUIRED_COLUMNS.join(', ')}`,
        },
      ],
    };
  }

  const index = Object.fromEntries(REQUIRED_COLUMNS.map((c) => [c, header.indexOf(c)]));

  const rows: ParsedRow[] = [];
  const errors: ImportRowError[] = [];

  lines.slice(1).forEach((line, i) => {
    // +2: первая строка — заголовок, нумерация строк для пользователя с единицы.
    const rowNumber = i + 2;
    const cells = splitLine(line);

    const rawAmount = cells[index.amount]?.replace(/\s/g, '').replace(',', '.');
    const parsed = csvRowSchema.safeParse({
      date: cells[index.date] ?? '',
      amount: rawAmount === '' || rawAmount === undefined ? NaN : Number(rawAmount),
      category: cells[index.category] ?? 'other',
      merchant: cells[index.merchant] ?? '',
    });

    if (parsed.success) {
      rows.push(parsed.data);
    } else {
      errors.push({
        row: rowNumber,
        message: parsed.error.issues.map((issue) => issue.message).join('; '),
      });
    }
  });

  return { rows, errors };
}
