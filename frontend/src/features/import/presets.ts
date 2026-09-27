import type { GoalDraft } from '@/shared/api/types';
import freelanceCsv from './presets/freelance.csv?raw';
import juniorCsv from './presets/junior.csv?raw';
import studentCsv from './presets/student.csv?raw';
import workerCsv from './presets/worker.csv?raw';

/**
 * Готовые выписки для проверки платформы.
 *
 * Составлены по образцу реальной банковской выписки: те же описания операций
 * («Автобусные линии 1», «YARCHE KRASNOJARSK RU», переводы по номеру телефона,
 * пополнения через СБП, кэшбэк), но все суммы и люди вымышлены.
 *
 * Четыре набора дают разные состояния продукта: спокойный месяц, «впритык»
 * после аренды, кассовый разрыв при нерегулярном доходе и растущие траты при цели,
 * которая к сроку не успевает. CSV лежат рядом
 * в `presets/` — их можно открыть и загрузить вручную тем же форматом.
 */
export interface DatasetPreset {
  id: string;
  title: string;
  /** Кто этот человек и из чего состоит выписка. */
  persona: string;
  /** Что на этом наборе стоит проверить. */
  check: string;
  fileName: string;
  csv: string;
  /** Баланс на сегодня — в CSV его нет, как и в строках банковской выписки. */
  balance: number;
  goals: GoalDraft[];
}

export const DATASET_PRESETS: DatasetPreset[] = [
  {
    id: 'student',
    title: 'Студентка на стипендии',
    persona:
      'Стипендия СФУ и помощь родителей по СБП, общежитие, связь. Мелкие траты: автобус по 48 ₽, «Ярче», аптека.',
    check: 'Спокойный месяц: календарь зелёный, справки по связи и общежитию, медленная цель.',
    fileName: 'student.csv',
    csv: studentCsv,
    balance: 4092,
    goals: [{ title: 'Новый телефон', targetAmount: 30000, savedAmount: 6000, deadline: '2027-03-01' }],
  },
  {
    id: 'worker',
    title: 'Подработка и съёмная квартира',
    persona:
      'Аванс и зарплата, аренда переводом по номеру телефона, фитнес и подписки. В сентябре — крупная покупка в М.Видео.',
    check: 'Впритык после аренды 1 октября, необычная трата в анализе, план накопления на отпуск.',
    fileName: 'worker.csv',
    csv: workerCsv,
    balance: 21000,
    goals: [{ title: 'Отпуск на Байкале', targetAmount: 45000, savedAmount: 12000, deadline: '2027-06-01' }],
  },
  {
    id: 'freelance',
    title: 'Нерегулярный доход',
    persona:
      'Заказы приходят по СБП в разные дни, стипендия, рассрочка «Сплит». Частые маркетплейсы, доставка и кафе.',
    check: 'Кассовый разрыв после аренды, «Могу купить?» отказывает, цель без срока — «данных недостаточно».',
    fileName: 'freelance.csv',
    csv: freelanceCsv,
    balance: 2300,
    goals: [{ title: 'Подушка безопасности', targetAmount: 20000, savedAmount: 500, deadline: null }],
  },
  {
    id: 'junior',
    title: 'Первая работа после учёбы',
    persona:
      'Зарплата раз в месяц 15-го, аренда 20-го, фитнес, курс в рассрочку и пять подписок. В сентябре — монитор в DNS, чаще такси и доставка.',
    check: 'Траты растут к прошлому месяцу, подписки за год, цель на ноутбук к сроку не успевает — что урезать.',
    fileName: 'junior.csv',
    csv: juniorCsv,
    balance: 9800,
    goals: [{ title: 'Ноутбук для работы', targetAmount: 90000, savedAmount: 15000, deadline: '2027-05-01' }],
  },
];
