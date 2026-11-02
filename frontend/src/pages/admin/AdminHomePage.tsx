import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiSend, type Role, ROLES, type User } from "../../api/client";
import { useResource } from "../../api/useResource";
import { ErrorText, Status } from "../../components/Status";

interface Brief {
  id: number;
  full_name: string;
}

interface AdminGroup {
  id: number;
  name: string;
  students: Brief[];
  teachers: Brief[];
}

interface AdminCourse {
  id: number;
  title: string;
  part: string;
  groups: Brief[];
  teachers: Brief[];
}

interface AuditEntry {
  id: number;
  created_at: string;
  actor_id: number | null;
  action: string;
  object_type: string | null;
  object_id: number | null;
  ip: string | null;
}

const TABS = ["users", "groups", "courses", "audit"] as const;
type Tab = (typeof TABS)[number];

/** Administrator cabinet (spec section 2, 14.1): users, groups, courses and the audit log. */
export function AdminHomePage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("users");
  return (
    <>
      <section className="card">
        <h1>{t("cabinet.admin")}</h1>
        <nav className="inline-form" aria-label={t("cabinet.admin")}>
          {TABS.map((name) => (
            <button
              key={name}
              type="button"
              aria-pressed={tab === name}
              onClick={() => setTab(name)}
            >
              {t(`admin.tabs.${name}`)}
            </button>
          ))}
        </nav>
      </section>
      {tab === "users" && <UsersSection />}
      {tab === "groups" && <GroupsSection />}
      {tab === "courses" && <CoursesSection />}
      {tab === "audit" && <AuditSection />}
    </>
  );
}

/** Runs an API call and keeps its error; `ok` is shown after success. */
function useAction() {
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState<string | null>(null);
  const run = async (call: () => Promise<unknown>, ok?: string) => {
    setError(null);
    setDone(null);
    try {
      await call();
      if (ok) setDone(ok);
      return true;
    } catch (caught) {
      setError(caught);
      return false;
    }
  };
  const feedback = (
    <>
      {done && <p>{done}</p>}
      {error !== null && <ErrorText error={error} />}
    </>
  );
  return { run, feedback };
}

function RoleBoxes({
  value,
  onChange,
}: {
  value: Role[];
  onChange: (roles: Role[]) => void;
}) {
  const { t } = useTranslation();
  return (
    <span>
      {ROLES.map((role) => (
        <label key={role} className="checkbox">
          <input
            type="checkbox"
            checked={value.includes(role)}
            onChange={(e) =>
              onChange(
                e.target.checked
                  ? [...value, role]
                  : value.filter((r) => r !== role),
              )
            }
          />
          {t(`roles.${role}`)}
        </label>
      ))}
    </span>
  );
}

// Users -----------------------------------------------------------------------------------

function UsersSection() {
  const { t } = useTranslation();
  const [q, setQ] = useState("");
  const [role, setRole] = useState<Role | "">("");
  const [filter, setFilter] = useState("");
  const users = useResource<User[]>(`/api/admin/users?limit=500${filter}`);

  const search = (event: FormEvent) => {
    event.preventDefault();
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    if (role) params.set("role", role);
    const query = params.toString();
    setFilter(query ? `&${query}` : "");
  };

  return (
    <>
      <CreateUserForm onCreated={users.reload} />
      <section className="card">
        <h2>{t("admin.users.title")}</h2>
        <form className="inline-form" onSubmit={search}>
          <label>
            {t("admin.users.search")}
            <input value={q} onChange={(e) => setQ(e.target.value)} />
          </label>
          <label>
            {t("admin.users.role")}
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as Role | "")}
            >
              <option value="">{t("admin.users.allRoles")}</option>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {t(`roles.${r}`)}
                </option>
              ))}
            </select>
          </label>
          <button type="submit">{t("admin.users.find")}</button>
        </form>
        <Status loading={users.loading} error={users.error} />
        {users.data?.length === 0 && (
          <p className="muted">{t("admin.users.none")}</p>
        )}
        <ul className="admin-list">
          {users.data?.map((u) => (
            <UserRow key={u.id} user={u} onChanged={users.reload} />
          ))}
        </ul>
      </section>
    </>
  );
}

function CreateUserForm({ onCreated }: { onCreated: () => void }) {
  const { t } = useTranslation();
  const empty = { email: "", full_name: "", password: "" };
  const [form, setForm] = useState(empty);
  const [roles, setRoles] = useState<Role[]>(["student"]);
  const { run, feedback } = useAction();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const ok = await run(
      () => apiSend("POST", "/api/admin/users", { ...form, roles }),
      t("admin.users.created"),
    );
    if (ok) {
      setForm(empty);
      onCreated();
    }
  };

  return (
    <section className="card">
      <h2>{t("admin.users.create")}</h2>
      <form className="inline-form" onSubmit={submit}>
        <label>
          {t("admin.users.fullName")}
          <input
            required
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
          />
        </label>
        <label>
          {t("login.email")}
          <input
            required
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
        </label>
        <label>
          {t("admin.users.password")}
          <input
            required
            type="password"
            minLength={12}
            autoComplete="new-password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </label>
        <RoleBoxes value={roles} onChange={setRoles} />
        <button type="submit" disabled={roles.length === 0}>
          {t("common.create")}
        </button>
      </form>
      <p className="muted">{t("admin.users.passwordHint")}</p>
      {feedback}
    </section>
  );
}

function UserRow({ user, onChanged }: { user: User; onChanged: () => void }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <li>
      <strong>{user.full_name}</strong> · {user.email} ·{" "}
      {user.roles.map((r) => t(`roles.${r}`)).join(", ")}
      {!user.is_active && (
        <span className="badge"> {t("admin.users.blocked")}</span>
      )}
      {user.two_factor_enabled && <span className="muted"> · 2FA</span>}{" "}
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
        {t("admin.users.manage")}
      </button>
      {open && <UserActions user={user} onChanged={onChanged} />}
    </li>
  );
}

function UserActions({
  user,
  onChanged,
}: {
  user: User;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const [roles, setRoles] = useState<Role[]>(user.roles);
  const [password, setPassword] = useState("");
  const [confirmAnonymize, setConfirmAnonymize] = useState(false);
  const { run, feedback } = useAction();
  const base = `/api/admin/users/${user.id}`;

  const act = async (call: () => Promise<unknown>, ok: string) => {
    if (await run(call, ok)) onChanged();
  };

  const savePassword = async (event: FormEvent) => {
    event.preventDefault();
    await act(
      () => apiSend("POST", `${base}/password`, { password }),
      t("admin.users.passwordSet"),
    );
    setPassword("");
  };

  return (
    <div className="card">
      <div className="inline-form">
        <RoleBoxes value={roles} onChange={setRoles} />
        <button
          type="button"
          disabled={roles.length === 0}
          onClick={() =>
            act(
              () => apiSend("PUT", `${base}/roles`, { roles }),
              t("common.saved"),
            )
          }
        >
          {t("admin.users.saveRoles")}
        </button>
      </div>
      <form className="inline-form" onSubmit={savePassword}>
        <label>
          {t("admin.users.newPassword")}
          <input
            required
            type="password"
            minLength={12}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <button type="submit">{t("admin.users.setPassword")}</button>
      </form>
      <div className="inline-form">
        <button
          type="button"
          onClick={() =>
            act(
              () =>
                apiSend("PUT", `${base}/active`, { active: !user.is_active }),
              t(
                user.is_active
                  ? "admin.users.blockedDone"
                  : "admin.users.unblockedDone",
              ),
            )
          }
        >
          {t(user.is_active ? "admin.users.block" : "admin.users.unblock")}
        </button>
        {user.two_factor_enabled && (
          <button
            type="button"
            onClick={() =>
              act(
                () => apiSend("POST", `${base}/2fa/reset`),
                t("admin.users.twoFactorReset"),
              )
            }
          >
            {t("admin.users.resetTwoFactor")}
          </button>
        )}
        {confirmAnonymize ? (
          <>
            <span role="alert">{t("admin.users.anonymizeWarning")}</span>
            <button
              type="button"
              onClick={() =>
                act(
                  () => apiSend("POST", `${base}/anonymize`),
                  t("common.saved"),
                )
              }
            >
              {t("admin.users.anonymizeConfirm")}
            </button>
            <button type="button" onClick={() => setConfirmAnonymize(false)}>
              {t("admin.cancel")}
            </button>
          </>
        ) : (
          <button type="button" onClick={() => setConfirmAnonymize(true)}>
            {t("admin.users.anonymize")}
          </button>
        )}
      </div>
      {feedback}
    </div>
  );
}

// Groups ----------------------------------------------------------------------------------

function UserPicker({
  role,
  exclude,
  onPick,
}: {
  role: Role;
  exclude: Brief[];
  onPick: (userId: number) => void;
}) {
  const { t } = useTranslation();
  const users = useResource<User[]>(`/api/admin/users?limit=500&role=${role}`);
  const [chosen, setChosen] = useState("");
  const taken = new Set(exclude.map((b) => b.id));
  const options = (users.data ?? []).filter(
    (u) => !taken.has(u.id) && u.is_active,
  );
  return (
    <span className="inline-form">
      <select
        aria-label={t(`admin.add.${role}`)}
        value={chosen}
        onChange={(e) => setChosen(e.target.value)}
      >
        <option value="">{t(`admin.add.${role}`)}</option>
        {options.map((u) => (
          <option key={u.id} value={u.id}>
            {u.full_name} ({u.email})
          </option>
        ))}
      </select>
      <button
        type="button"
        disabled={!chosen}
        onClick={() => {
          onPick(Number(chosen));
          setChosen("");
        }}
      >
        {t("admin.add.button")}
      </button>
    </span>
  );
}

function PeopleList({
  people,
  onRemove,
}: {
  people: Brief[];
  onRemove: (id: number) => void;
}) {
  const { t } = useTranslation();
  if (people.length === 0) return <p className="muted">{t("admin.empty")}</p>;
  return (
    <ul>
      {people.map((p) => (
        <li key={p.id}>
          {p.full_name}{" "}
          <button type="button" onClick={() => onRemove(p.id)}>
            {t("common.remove")}
          </button>
        </li>
      ))}
    </ul>
  );
}

function GroupsSection() {
  const { t } = useTranslation();
  const groups = useResource<AdminGroup[]>("/api/admin/groups");
  const [name, setName] = useState("");
  const { run, feedback } = useAction();

  const act = async (call: () => Promise<unknown>) => {
    if (await run(call)) groups.reload();
  };

  const create = async (event: FormEvent) => {
    event.preventDefault();
    await act(() => apiSend("POST", "/api/admin/groups", { name }));
    setName("");
  };

  return (
    <>
      <section className="card">
        <h2>{t("admin.groups.create")}</h2>
        <form className="inline-form" onSubmit={create}>
          <label>
            {t("admin.groups.name")}
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <button type="submit">{t("common.create")}</button>
        </form>
        {feedback}
      </section>
      <Status loading={groups.loading} error={groups.error} />
      {groups.data?.length === 0 && <p className="muted">{t("admin.empty")}</p>}
      {groups.data?.map((g) => {
        const path = `/api/admin/groups/${g.id}`;
        return (
          <section className="card" key={g.id}>
            <h2>{g.name}</h2>
            <h3>{t("admin.groups.students")}</h3>
            <PeopleList
              people={g.students}
              onRemove={(id) =>
                act(() => apiSend("DELETE", `${path}/members/${id}`))
              }
            />
            <UserPicker
              role="student"
              exclude={g.students}
              onPick={(id) =>
                act(() => apiSend("POST", `${path}/members`, { user_id: id }))
              }
            />
            <h3>{t("admin.groups.teachers")}</h3>
            <PeopleList
              people={g.teachers}
              onRemove={(id) =>
                act(() => apiSend("DELETE", `${path}/teachers/${id}`))
              }
            />
            <UserPicker
              role="teacher"
              exclude={g.teachers}
              onPick={(id) =>
                act(() => apiSend("POST", `${path}/teachers`, { user_id: id }))
              }
            />
          </section>
        );
      })}
    </>
  );
}

// Courses ---------------------------------------------------------------------------------

function CoursesSection() {
  const { t } = useTranslation();
  const courses = useResource<AdminCourse[]>("/api/admin/courses");
  const groups = useResource<AdminGroup[]>("/api/admin/groups");
  const [chosen, setChosen] = useState<Record<number, string>>({});
  const { run, feedback } = useAction();

  const act = async (call: () => Promise<unknown>) => {
    if (await run(call)) courses.reload();
  };

  return (
    <>
      <section className="card">
        <h2>{t("admin.courses.title")}</h2>
        <p className="muted">{t("admin.courses.hint")}</p>
        {feedback}
      </section>
      <Status loading={courses.loading} error={courses.error} />
      {courses.data?.map((c) => {
        const attached = new Set(c.groups.map((g) => g.id));
        const free = (groups.data ?? []).filter((g) => !attached.has(g.id));
        return (
          <section className="card" key={c.id}>
            <h2>{c.title}</h2>
            <h3>{t("admin.courses.groups")}</h3>
            <PeopleList
              people={c.groups}
              onRemove={(id) =>
                act(() =>
                  apiSend("DELETE", `/api/admin/courses/${c.id}/groups/${id}`),
                )
              }
            />
            <span className="inline-form">
              <select
                aria-label={t("admin.add.group")}
                value={chosen[c.id] ?? ""}
                onChange={(e) =>
                  setChosen({ ...chosen, [c.id]: e.target.value })
                }
              >
                <option value="">{t("admin.add.group")}</option>
                {free.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                disabled={!chosen[c.id]}
                onClick={() => {
                  const id = Number(chosen[c.id]);
                  setChosen({ ...chosen, [c.id]: "" });
                  void act(() =>
                    apiSend("POST", `/api/courses/${c.id}/groups`, { id }),
                  );
                }}
              >
                {t("admin.add.button")}
              </button>
            </span>
            <h3>{t("admin.courses.teachers")}</h3>
            <PeopleList
              people={c.teachers}
              onRemove={(id) =>
                act(() =>
                  apiSend(
                    "DELETE",
                    `/api/admin/courses/${c.id}/teachers/${id}`,
                  ),
                )
              }
            />
            <UserPicker
              role="teacher"
              exclude={c.teachers}
              onPick={(id) =>
                act(() =>
                  apiSend("POST", `/api/courses/${c.id}/teachers`, { id }),
                )
              }
            />
          </section>
        );
      })}
    </>
  );
}

// Audit log -------------------------------------------------------------------------------

function AuditSection() {
  const { t } = useTranslation();
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const [filter, setFilter] = useState("");
  const rows = useResource<AuditEntry[]>(
    `/api/admin/audit-log?limit=200${filter}`,
  );

  const apply = (event: FormEvent) => {
    event.preventDefault();
    const params = new URLSearchParams();
    if (action.trim()) params.set("action", action.trim());
    if (actor.trim()) params.set("actor_id", actor.trim());
    const query = params.toString();
    setFilter(query ? `&${query}` : "");
  };

  return (
    <section className="card">
      <h2>{t("admin.audit.title")}</h2>
      <form className="inline-form" onSubmit={apply}>
        <label>
          {t("admin.audit.action")}
          <input
            value={action}
            placeholder="login_failed"
            onChange={(e) => setAction(e.target.value)}
          />
        </label>
        <label>
          {t("admin.audit.actor")}
          <input
            type="number"
            min={1}
            value={actor}
            onChange={(e) => setActor(e.target.value)}
          />
        </label>
        <button type="submit">{t("admin.users.find")}</button>
      </form>
      <Status loading={rows.loading} error={rows.error} />
      <table>
        <thead>
          <tr>
            <th>{t("admin.audit.when")}</th>
            <th>{t("admin.audit.actor")}</th>
            <th>{t("admin.audit.action")}</th>
            <th>{t("admin.audit.object")}</th>
            <th>IP</th>
          </tr>
        </thead>
        <tbody>
          {rows.data?.map((r) => (
            <tr key={r.id}>
              <td>{new Date(r.created_at).toLocaleString()}</td>
              <td>{r.actor_id ?? "—"}</td>
              <td>{r.action}</td>
              <td>
                {r.object_type ? `${r.object_type} #${r.object_id ?? ""}` : "—"}
              </td>
              <td>{r.ip ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
