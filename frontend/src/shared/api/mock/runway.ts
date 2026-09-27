import type {
  CategoryId,
  ImpulseCheck,
  Profile,
  Runway,
  RunwayDay,
  UpcomingIncome,
} from '../types';

/**
 * Календарь кассовых разрывов и проверка импульсной покупки.
 *
 * Один расчёт на обе фичи: иначе «можно 400 ₽ в день» и «покупка за 4 900 ₽»
 * будут врать друг другу. Точные числа считает код, не модель.
 */

export interface LedgerEvent {
  date: string;
  title: string;
  amount: number;
  category: CategoryId;
}

const TIGHT_FLOOR = 2000;

export function parseIso(iso: string) {
  const [year, month, day] = iso.split('-').map(Number);
  return new Date(year, month - 1, day);
}

export function toIso(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function addDays(iso: string, days: number) {
  const date = parseIso(iso);
  date.setDate(date.getDate() + days);
  return toIso(date);
}

export function daysBetween(from: string, to: string) {
  return Math.round((parseIso(to).getTime() - parseIso(from).getTime()) / 86_400_000);
}

/** Платёж на 31-е в коротком месяце приходится на последний день месяца. */
function onDayOf(year: number, month: number, dayOfMonth: number) {
  const last = new Date(year, month + 1, 0).getDate();
  return new Date(year, month, Math.min(dayOfMonth, last));
}

/** Приходится ли регулярная операция с этим числом месяца на указанную дату. */
export function occursOn(dayOfMonth: number, iso: string) {
  const date = parseIso(iso);
  return toIso(onDayOf(date.getFullYear(), date.getMonth(), dayOfMonth)) === iso;
}

function nextOnDay(today: string, dayOfMonth: number) {
  const date = parseIso(today);
  let candidate = onDayOf(date.getFullYear(), date.getMonth(), dayOfMonth);
  if (toIso(candidate) <= today) {
    candidate = onDayOf(date.getFullYear(), date.getMonth() + 1, dayOfMonth);
  }
  return toIso(candidate);
}

export function plannedEvents(profile: Profile, today: string): LedgerEvent[] {
  const bills = profile.autopayments.map((bill) => ({
    date: nextOnDay(today, bill.dayOfMonth),
    title: bill.title,
    amount: -bill.amount,
    category: bill.category,
  }));

  const incoming = profile.incomes.map((income) => ({
    date: nextOnDay(today, income.dayOfMonth),
    title: income.title,
    amount: income.amount,
    category: 'other' as const,
  }));

  return [...bills, ...incoming].sort((a, b) => a.date.localeCompare(b.date) || a.title.localeCompare(b.title));
}

function statusOf(balance: number): RunwayDay['status'] {
  if (balance < 0) return 'shortfall';
  if (balance < TIGHT_FLOOR) return 'tight';
  return 'ok';
}

function simulate(args: {
  today: string;
  balance: number;
  events: LedgerEvent[];
  impulse?: { amount: number; date: string };
  horizonEnd: string;
}): RunwayDay[] {
  const { today, events, impulse, horizonEnd } = args;
  let balance = args.balance;
  const days: RunwayDay[] = [];

  for (let date = today; date <= horizonEnd; date = addDays(date, 1)) {
    const dayEvents = events
      .filter((event) => event.date === date)
      .map((event) => ({ title: event.title, amount: event.amount }));

    if (impulse && impulse.date === date && impulse.amount > 0) {
      dayEvents.push({ title: 'Покупка', amount: -impulse.amount });
    }

    for (const event of dayEvents) balance += event.amount;

    days.push({
      date,
      events: dayEvents,
      balance,
      status: statusOf(balance),
    });
  }

  return days;
}

function firstIncome(events: LedgerEvent[], after: string): UpcomingIncome | null {
  const found = events.find((event) => event.amount > 0 && event.date > after);
  if (!found) return null;
  return {
    date: found.date,
    title: found.title,
    amount: found.amount,
    daysUntil: daysBetween(after, found.date),
  };
}

function safeDailySpend(balance: number, events: LedgerEvent[], today: string, until: string) {
  const days = Math.max(daysBetween(today, until), 1);
  const bills = events
    .filter((event) => event.amount < 0 && event.date > today && event.date < until)
    .reduce((sum, event) => sum + event.amount, 0);
  return Math.max(0, Math.floor((balance + bills) / days));
}

function summarize(days: RunwayDay[]) {
  return {
    redDays: days.filter((day) => day.status === 'shortfall').length,
    lowestBalance: days.reduce((min, day) => Math.min(min, day.balance), Number.POSITIVE_INFINITY),
  };
}

export function buildRunway(profile: Profile, today: string): Runway {
  const events = plannedEvents(profile, today);
  const nextIncome = firstIncome(events, today);
  const horizonEnd = events[events.length - 1]?.date ?? addDays(today, 14);
  const days = simulate({
    today,
    balance: profile.balance,
    events,
    horizonEnd,
  });
  const until = nextIncome?.date ?? horizonEnd;

  return {
    horizonTo: horizonEnd,
    nextIncome,
    todaySafeSpend: safeDailySpend(profile.balance, events, today, until),
    ...summarize(days),
    days,
  };
}

export function buildImpulse(
  profile: Profile,
  today: string,
  amount: number,
  /** Сколько в месяц реально остаётся на цель; null — не откладывается ничего. */
  monthlyPace: number | null,
): ImpulseCheck {
  const events = plannedEvents(profile, today);
  const nextIncome = firstIncome(events, today);
  const horizonEnd = events[events.length - 1]?.date ?? addDays(today, 14);
  const until = nextIncome?.date ?? horizonEnd;

  const beforeDays = simulate({ today, balance: profile.balance, events, horizonEnd });
  const afterDays = simulate({
    today,
    balance: profile.balance,
    events,
    horizonEnd,
    impulse: { amount, date: today },
  });

  const before = summarize(beforeDays);
  const after = summarize(afterDays);
  const todaySafeSpendBefore = safeDailySpend(profile.balance, events, today, until);
  const todaySafeSpendAfter = safeDailySpend(profile.balance - amount, events, today, until);

  let verdict: ImpulseCheck['verdict'] = 'ok';
  if (after.lowestBalance < 0) verdict = 'shortfall';
  else if (
    after.redDays > before.redDays ||
    (after.lowestBalance < TIGHT_FLOOR && before.lowestBalance >= TIGHT_FLOOR)
  ) {
    verdict = 'wait';
  }

  let waitUntil: UpcomingIncome | null = null;
  if (verdict !== 'ok') {
    const incomes = events.filter((event) => event.amount > 0 && event.date > today);
    for (const income of incomes) {
      const trial = summarize(
        simulate({
          today,
          balance: profile.balance,
          events,
          horizonEnd,
          impulse: { amount, date: income.date },
        }),
      );
      if (trial.lowestBalance >= 0) {
        waitUntil = {
          date: income.date,
          title: income.title,
          amount: income.amount,
          daysUntil: daysBetween(today, income.date),
        };
        break;
      }
    }
  }

  const goal = profile.goals.find((item) => item.deadline && item.savedAmount < item.targetAmount);
  const dailyPace = monthlyPace && monthlyPace > 0 ? monthlyPace / 30 : null;
  const goalImpact = goal && dailyPace
    ? {
        goalTitle: goal.title,
        delayDays: Math.max(1, Math.ceil(amount / dailyPace)),
      }
    : null;

  const hint =
    verdict === 'ok'
      ? `Покупка влезает: дневной лимит станет ${todaySafeSpendAfter.toLocaleString('ru-RU')} ₽, обязательные платежи не пострадают.`
      : verdict === 'wait' && waitUntil
        ? `Лучше подождать до «${waitUntil.title}» ${formatHuman(waitUntil.date)} — тогда покупка не сожмёт дни до поступления.`
        : waitUntil
          ? `Сейчас не влезет: после обязательных платежей баланс уйдёт в минус. Подождите «${waitUntil.title}» ${formatHuman(waitUntil.date)}.`
          : 'Сейчас не влезет: после обязательных платежей не хватит денег. Покупку лучше отложить.';

  return {
    amount,
    verdict,
    hint,
    todaySafeSpendBefore,
    todaySafeSpendAfter,
    redDaysBefore: before.redDays,
    redDaysAfter: after.redDays,
    lowestBalanceAfter: after.lowestBalance,
    waitUntil,
    goalImpact,
    daysAfter: afterDays,
  };
}

function formatHuman(iso: string) {
  return parseIso(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}
