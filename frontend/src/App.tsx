import { FormEvent, useEffect, useState } from "react";
import { api, participantHeaders } from "./api";

type Exercise = {
  id: number;
  title: string;
  generation_prompt: string;
  status: string;
  join_code: string | null;
  initial_count: number;
  refill_threshold: number;
  min_answers: number;
  ema_threshold: string;
  alpha: string;
  questions?: Question[];
  jobs?: Job[];
};

type Question = {
  id: number;
  text: string;
  status: string;
  expected_answer: string;
  absolute_tolerance: string;
  relative_tolerance: string;
};

type Job = { id: number; status: string; error: string | null; requested_count: number };
type Progress = { id: number; display_name: string; answer_count: number; ema: string | null; achieved: boolean };

function ErrorMessage({ message }: { message: string }) {
  return message ? <p className="error" role="alert">{message}</p> : null;
}

function Landing({ onTeacher }: { onTeacher: () => void }) {
  const [joinCode, setJoinCode] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [joined, setJoined] = useState(Boolean(sessionStorage.getItem("participantToken")));

  async function join(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const result = await api<{ token: string }>("/api/participant/join", {
        method: "POST",
        body: JSON.stringify({ join_code: joinCode, display_name: name }),
      });
      sessionStorage.setItem("participantToken", result.token);
      setJoined(true);
    } catch (cause) {
      setError((cause as Error).message);
    }
  }

  if (joined) return <Practice onLeave={() => { sessionStorage.removeItem("participantToken"); setJoined(false); }} />;

  return (
    <main className="shell landing">
      <section className="hero">
        <p className="eyebrow">MASTER THROUGH REPETITION</p>
        <h1>Practice<span>Hell</span></h1>
        <p className="tagline">身につくまで、終わらない。</p>
      </section>
      <section className="card join-card">
        <div className="card-number">01</div>
        <h2>演習に参加</h2>
        <p className="muted">教師から共有されたコードを入力してください。</p>
        <form onSubmit={join}>
          <label>参加コード<input value={joinCode} onChange={(e) => setJoinCode(e.target.value.toUpperCase())} placeholder="ABC123" required /></label>
          <label>表示名<input value={name} onChange={(e) => setName(e.target.value)} placeholder="山田 太郎" required /></label>
          <ErrorMessage message={error} />
          <button className="primary" type="submit">演習を始める <span>→</span></button>
        </form>
        <button className="text-button" onClick={onTeacher}>教師としてログイン</button>
      </section>
    </main>
  );
}

function Practice({ onLeave }: { onLeave: () => void }) {
  const [question, setQuestion] = useState<{ id: number; text: string } | null>(null);
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState<{ correct: boolean; expected_answer: string; answer_count: number; ema: string; achieved: boolean } | null>(null);
  const [error, setError] = useState("");

  async function loadNext() {
    setError(""); setFeedback(null); setAnswer("");
    try {
      const result = await api<{ question: { id: number; text: string } }>("/api/participant/next", { headers: participantHeaders() });
      setQuestion(result.question);
    } catch (cause) { setError((cause as Error).message); }
  }

  useEffect(() => { void loadNext(); }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!question) return;
    try {
      const result = await api<typeof feedback>("/api/participant/answer", {
        method: "POST", headers: participantHeaders(), body: JSON.stringify({ question_id: question.id, answer }),
      });
      setFeedback(result);
    } catch (cause) { setError((cause as Error).message); }
  }

  return (
    <main className="shell practice-shell">
      <header className="topbar"><strong>Practice<span>Hell</span></strong><button className="text-button" onClick={onLeave}>退出</button></header>
      <section className="practice-panel">
        <p className="eyebrow">NUMERIC ANSWER</p>
        {question ? <h2>{question.text}</h2> : <h2>問題を準備しています…</h2>}
        {!feedback && question && <form onSubmit={submit} className="answer-form"><label>あなたの解答<input autoFocus inputMode="decimal" value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="数値を入力" required /></label><button className="primary">解答する</button></form>}
        {feedback && <div className={`feedback ${feedback.correct ? "correct" : "wrong"}`}><p className="result">{feedback.correct ? "正解" : "不正解"}</p><p>正答: <strong>{feedback.expected_answer}</strong></p><div className="stats"><span>{feedback.answer_count}<small>解答数</small></span><span>{(Number(feedback.ema) * 100).toFixed(1)}%<small>EMA</small></span></div>{feedback.achieved && <p className="achieved">習熟基準を達成しました！</p>}<button className="primary" onClick={() => void loadNext()}>次の問題へ →</button></div>}
        <ErrorMessage message={error} />
      </section>
    </main>
  );
}

function Teacher({ onBack }: { onBack: () => void }) {
  const [loggedIn, setLoggedIn] = useState(false);
  const [password, setPassword] = useState("");
  const [exercises, setExercises] = useState<Exercise[]>([]);
  const [selected, setSelected] = useState<Exercise | null>(null);
  const [progress, setProgress] = useState<Progress[]>([]);
  const [error, setError] = useState("");

  async function loadExercises() {
    try { setExercises(await api<Exercise[]>("/api/teacher/exercises")); setLoggedIn(true); }
    catch { setLoggedIn(false); }
  }
  useEffect(() => { void loadExercises(); }, []);

  async function login(event: FormEvent) {
    event.preventDefault(); setError("");
    try { await api("/api/teacher/login", { method: "POST", body: JSON.stringify({ password }) }); await loadExercises(); }
    catch (cause) { setError((cause as Error).message); }
  }

  async function openExercise(id: number) {
    setError("");
    try {
      setSelected(await api<Exercise>(`/api/teacher/exercises/${id}`));
      setProgress(await api<Progress[]>(`/api/teacher/exercises/${id}/progress`));
    } catch (cause) { setError((cause as Error).message); }
  }

  if (!loggedIn) return <main className="shell center"><section className="card login-card"><p className="eyebrow">FACILITATOR</p><h2>教師ログイン</h2><form onSubmit={login}><label>共通パスワード<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label><ErrorMessage message={error} /><button className="primary">ログイン</button></form><button className="text-button" onClick={onBack}>参加画面へ戻る</button></section></main>;

  return (
    <main className="admin-shell">
      <header className="topbar"><strong>Practice<span>Hell</span> / 教師</strong><button className="text-button" onClick={onBack}>参加画面</button></header>
      <div className="admin-grid">
        <aside><button className="primary" onClick={() => setSelected(null)}>＋ 新しい演習</button><h3>演習一覧</h3>{exercises.map((item) => <button key={item.id} className="exercise-link" onClick={() => void openExercise(item.id)}><span>{item.title}</span><small>{item.status}{item.join_code ? ` · ${item.join_code}` : ""}</small></button>)}</aside>
        <section className="admin-main">{selected ? <ExerciseDetail exercise={selected} progress={progress} refresh={() => openExercise(selected.id)} /> : <ExerciseForm created={async (exercise) => { await loadExercises(); await openExercise(exercise.id); }} />}<ErrorMessage message={error} /></section>
      </div>
    </main>
  );
}

function ExerciseForm({ created }: { created: (exercise: Exercise) => void }) {
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const data = new FormData(event.currentTarget);
    try {
      const exercise = await api<Exercise>("/api/teacher/exercises", { method: "POST", body: JSON.stringify({ title: data.get("title"), generation_prompt: data.get("prompt"), initial_count: Number(data.get("initial_count")), refill_threshold: 10, min_answers: Number(data.get("min_answers")), ema_threshold: data.get("ema_threshold"), alpha: data.get("alpha"), default_absolute_tolerance: data.get("absolute_tolerance"), default_relative_tolerance: data.get("relative_tolerance") }) });
      created(exercise);
    } catch (cause) { setError((cause as Error).message); }
  }
  return <section><p className="eyebrow">NEW EXERCISE</p><h1>演習を作成</h1><form className="form-grid" onSubmit={submit}><label className="wide">タイトル<input name="title" required /></label><label className="wide">問題生成の指示<textarea name="prompt" rows={5} placeholder="例: 高校物理の等加速度運動。SI単位で答える問題。" required /></label><label>初期問題数<input name="initial_count" type="number" defaultValue="30" min="1" max="100" /></label><label>最低解答数<input name="min_answers" type="number" defaultValue="20" min="1" /></label><label>EMA閾値<input name="ema_threshold" defaultValue="0.8" /></label><label>α<input name="alpha" defaultValue="0.2" /></label><label>絶対許容誤差<input name="absolute_tolerance" defaultValue="0" /></label><label>相対許容誤差<input name="relative_tolerance" defaultValue="0" /></label><ErrorMessage message={error} /><button className="primary wide">作成する</button></form></section>;
}

function ExerciseDetail({ exercise, progress, refresh }: { exercise: Exercise; progress: Progress[]; refresh: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function action(path: string) { setBusy(true); setError(""); try { await api(path, { method: "POST" }); await refresh(); } catch (cause) { setError((cause as Error).message); } finally { setBusy(false); } }
  return <section><div className="detail-head"><div><p className="eyebrow">{exercise.status.toUpperCase()}</p><h1>{exercise.title}</h1></div>{exercise.join_code && <div className="join-code"><small>参加コード</small><strong>{exercise.join_code}</strong></div>}</div><p className="prompt-box">{exercise.generation_prompt}</p><div className="actions"><button className="secondary" disabled={busy} onClick={() => void action(`/api/teacher/exercises/${exercise.id}/generate`)}>問題を生成</button><button className="primary" disabled={busy} onClick={() => void action(`/api/teacher/exercises/${exercise.id}/publish`)}>公開する</button>{exercise.status === "published" && <button className="danger" onClick={() => void action(`/api/teacher/exercises/${exercise.id}/close`)}>終了</button>}<button className="text-button" onClick={() => void refresh()}>更新</button></div><ErrorMessage message={error} />{exercise.jobs?.[0]?.status === "failed" && <p className="error">生成失敗: {exercise.jobs[0].error}</p>}<h2>生成問題 <span className="count">{exercise.questions?.length ?? 0}</span></h2><div className="questions">{exercise.questions?.map((question) => <QuestionEditor key={question.id} question={question} refresh={refresh} />)}</div><h2>参加者の進捗</h2>{progress.length ? <table><thead><tr><th>表示名</th><th>解答数</th><th>EMA</th><th>状態</th></tr></thead><tbody>{progress.map((item) => <tr key={item.id}><td>{item.display_name}</td><td>{item.answer_count}</td><td>{item.ema ? `${(Number(item.ema) * 100).toFixed(1)}%` : "—"}</td><td>{item.achieved ? "達成" : "演習中"}</td></tr>)}</tbody></table> : <p className="muted">まだ参加者はいません。</p>}</section>;
}

function QuestionEditor({ question, refresh }: { question: Question; refresh: () => Promise<void> }) {
  const [draft, setDraft] = useState(question);
  async function save(status = draft.status) { await api(`/api/teacher/questions/${question.id}`, { method: "PATCH", body: JSON.stringify({ ...draft, status, id: undefined }) }); await refresh(); }
  return <article className={`question ${question.status}`}><textarea value={draft.text} onChange={(e) => setDraft({ ...draft, text: e.target.value })} /><div className="question-values"><label>正答<input value={draft.expected_answer} onChange={(e) => setDraft({ ...draft, expected_answer: e.target.value })} /></label><label>絶対誤差<input value={draft.absolute_tolerance} onChange={(e) => setDraft({ ...draft, absolute_tolerance: e.target.value })} /></label><label>相対誤差<input value={draft.relative_tolerance} onChange={(e) => setDraft({ ...draft, relative_tolerance: e.target.value })} /></label></div><div className="actions"><button className="secondary" onClick={() => void save()}>保存</button><button className="approve" onClick={() => void save("approved")}>承認</button><button className="text-button" onClick={() => void save("rejected")}>却下</button><small>{question.status}</small></div></article>;
}

export default function App() {
  const [teacher, setTeacher] = useState(location.hash === "#teacher");
  function switchMode(next: boolean) { location.hash = next ? "teacher" : ""; setTeacher(next); }
  return teacher ? <Teacher onBack={() => switchMode(false)} /> : <Landing onTeacher={() => switchMode(true)} />;
}
