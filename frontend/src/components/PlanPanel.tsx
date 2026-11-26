import type { Todo } from "../api";

const LABEL = { pending: "To do", in_progress: "In progress", completed: "Done" };

export function PlanPanel({ plan }: { plan: Todo[] }) {
  const done = plan.filter((todo) => todo.status === "completed").length;
  return (
    <section className="plan" aria-label="Plan">
      <h2>
        Plan {plan.length > 0 && <span className="count">{done} of {plan.length} done</span>}
      </h2>
      {plan.length === 0 ? (
        <p className="empty">The Sidekick writes its plan here as it works.</p>
      ) : (
        <ol>
          {plan.map((todo, i) => (
            <li key={i} className={todo.status}>
              <span className="mark" aria-label={LABEL[todo.status]} />
              {todo.content}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
