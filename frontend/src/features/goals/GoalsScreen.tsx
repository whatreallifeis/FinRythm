import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Screen } from '@/layouts/Screen';
import { usePlatform } from '@/platform';
import {
  useCreateGoal,
  useDeleteGoal,
  useGoalPlan,
  useProfile,
  useUpdateGoal,
} from '@/shared/api/hooks';
import type { Goal, GoalDraft } from '@/shared/api/types';
import { categoryLabel } from '@/shared/lib/categories';
import { formatDateFull, formatMoney, pluralMonths } from '@/shared/lib/format';
import { Button, Card, CardTitle, EmptyState, ScreenState, SkeletonCard } from '@/shared/ui';
import { ExplainedView } from '@/features/explain/ExplainedView';
import { GoalForm } from './GoalForm';
import { GoalMenu } from './GoalMenu';

type Editor = { mode: 'create' } | { mode: 'edit'; goal: Goal };

export function GoalsScreen() {
  const navigate = useNavigate();
  const { haptic } = usePlatform();
  const profile = useProfile();
  const createGoal = useCreateGoal();
  const updateGoal = useUpdateGoal();
  const deleteGoal = useDeleteGoal();

  const [activeGoalId, setActiveGoalId] = useState<string | null>(null);
  const [editor, setEditor] = useState<Editor | null>(null);
  const plan = useGoalPlan(activeGoalId);

  const closeEditor = () => setEditor(null);

  const handleCreate = (draft: GoalDraft) => {
    createGoal.mutate(draft, {
      onSuccess: () => {
        haptic('success');
        closeEditor();
      },
      onError: () => haptic('error'),
    });
  };

  const handleUpdate = (id: string, draft: GoalDraft) => {
    updateGoal.mutate(
      { id, draft },
      {
        onSuccess: () => {
          haptic('success');
          closeEditor();
        },
        onError: () => haptic('error'),
      },
    );
  };

  const handleDelete = (id: string) => {
    deleteGoal.mutate(id, {
      onSuccess: () => {
        if (activeGoalId === id) setActiveGoalId(null);
        haptic('success');
      },
      onError: () => haptic('error'),
    });
  };

  if (editor) {
    return (
      <Screen title="Цели" subtitle={editor.mode === 'edit' ? 'Изменение цели' : 'Новая цель'}>
        <GoalForm
          goal={editor.mode === 'edit' ? editor.goal : undefined}
          loading={createGoal.isPending || updateGoal.isPending}
          error={
            (editor.mode === 'create' ? createGoal.error : updateGoal.error)?.message ?? null
          }
          onSubmit={(draft) =>
            editor.mode === 'edit' ? handleUpdate(editor.goal.id, draft) : handleCreate(draft)
          }
          onCancel={closeEditor}
        />
      </Screen>
    );
  }

  return (
    <Screen
      title="Цели"
      subtitle="Накопления и срок их достижения"
      action={
        <Button size="sm" onClick={() => setEditor({ mode: 'create' })}>
          Добавить цель
        </Button>
      }
    >
      <ScreenState
        query={profile}
        isEmpty={(data) => data.goals.length === 0}
        skeleton={<SkeletonCard />}
        empty={
          <EmptyState
            title="Целей пока нет"
            description="Добавьте цель — появится темп накопления и срок"
            action={
              <Button size="sm" onClick={() => setEditor({ mode: 'create' })}>
                Добавить цель
              </Button>
            }
          />
        }
      >
        {(data) => (
          <div className="space-y-3">
            {data.goals.map((goal) => {
              const progress = goal.targetAmount === 0 ? 0 : goal.savedAmount / goal.targetAmount;
              const isActive = goal.id === activeGoalId;

              return (
                <Card key={goal.id}>
                  <CardTitle
                    action={
                      <div className="flex items-center gap-1">
                        <GoalMenu
                          deleting={deleteGoal.isPending && deleteGoal.variables === goal.id}
                          onEdit={() => setEditor({ mode: 'edit', goal })}
                          onDelete={() => handleDelete(goal.id)}
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setActiveGoalId(isActive ? null : goal.id)}
                        >
                          {isActive ? 'Свернуть' : 'Разобрать'}
                        </Button>
                      </div>
                    }
                  >
                    {goal.title}
                  </CardTitle>

                  <div className="mb-2 flex items-baseline justify-between text-sm">
                    <span className="tabular font-medium">{formatMoney(goal.savedAmount)}</span>
                    <span className="tabular text-muted">из {formatMoney(goal.targetAmount)}</span>
                  </div>

                  <div className="h-2 overflow-hidden rounded-full bg-surface-hover">
                    <div
                      className="h-full rounded-full bg-accent"
                      style={{ width: `${Math.min(progress, 1) * 100}%` }}
                    />
                  </div>

                  <p className="mt-2 text-xs text-muted">
                    {goal.deadline ? `Срок: ${formatDateFull(goal.deadline)}` : 'Срок не задан'}
                  </p>

                  {isActive && (
                    <div className="mt-4 border-t border-border pt-4">
                      <ExplainedView
                        query={plan}
                        insufficientAction={
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => navigate('/app/import')}
                          >
                            Дозаполнить данные
                          </Button>
                        }
                      >
                        {(result) => (
                          <div className="space-y-3">
                            <div className="flex gap-4 text-sm">
                              <div>
                                <p className="text-muted">Темп</p>
                                <p className="tabular font-medium">
                                  {formatMoney(result.monthlyPace)} / мес
                                </p>
                              </div>
                              <div>
                                <p className="text-muted">Срок</p>
                                <p className="font-medium">
                                  {result.etaMonths ? pluralMonths(result.etaMonths) : '—'}
                                </p>
                              </div>
                            </div>

                            {result.blockers.length > 0 && (
                              <div>
                                <p className="mb-1.5 text-sm font-medium">Что отодвигает цель</p>
                                <ul className="space-y-2 text-sm">
                                  {result.blockers.map((blocker) => (
                                    <li key={blocker.category} className="text-muted">
                                      <span className="text-text">
                                        {categoryLabel(blocker.category)} —{' '}
                                        {formatMoney(blocker.amount)}
                                      </span>
                                      <br />
                                      {blocker.hint}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </div>
                        )}
                      </ExplainedView>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        )}
      </ScreenState>
    </Screen>
  );
}
