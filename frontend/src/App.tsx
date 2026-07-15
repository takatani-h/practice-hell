import { FormEvent, useEffect, useState } from "react";
import { api, sessionHeaders } from "./api";
import MathText from "./MathText";
import type { Exercise, Feedback, Question } from "./types";

function Message({ text, kind = "error" }: { text: string; kind?: "error" | "info" }) {
  return text ? <p className={`message ${kind}`} role="status">{text}</p> : null;
}

function AttendanceForm({ exercise, onJoined }: { exercise: Exercise; onJoined: () => void }) {
  const [studentNumber, setStudentNumber] = useState("");
  const [studentName, setStudentName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const result = await api<{ token: string }>("/api/sessions", {
        method: "POST",
        body: JSON.stringify({
          join_code: exercise.join_code,
          student_number: studentNumber,
          student_name: studentName,
        }),
      });
      sessionStorage.setItem("practiceHellToken", result.token);
      sessionStorage.setItem("practiceHellJoinCode", exercise.join_code);
      onJoined();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section>
      <h1>{exercise.title}</h1>
      <p>出席番号と名前を入力してください。</p>
      <form onSubmit={submit}>
        <label>出席番号<input value={studentNumber} onChange={(e) => setStudentNumber(e.target.value)} required autoFocus /></label>
        <label>名前<input value={studentName} onChange={(e) => setStudentName(e.target.value)} required /></label>
        <Message text={error} />
        <button type="submit" disabled={loading}>{loading ? "最初の問題を生成しています…" : "演習を始める"}</button>
      </form>
    </section>
  );
}

function Practice({ exercise }: { exercise: Exercise }) {
  const [question, setQuestion] = useState<Question | null>(null);
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadQuestion() {
    setLoading(true);
    setError("");
    setFeedback(null);
    setAnswer("");
    try {
      const result = await api<Question>("/api/session/question", { headers: sessionHeaders() });
      setQuestion(result);
    } catch (cause) {
      setQuestion(null);
      setError((cause as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadQuestion(); }, []);

  useEffect(() => {
    if (!feedback || feedback.next_question_ready) return;

    let cancelled = false;
    let timer: number | undefined;
    async function checkNextQuestion() {
      try {
        const status = await api<{ ready: boolean }>("/api/session/question-status", {
          headers: sessionHeaders(),
        });
        if (cancelled) return;
        if (status.ready) {
          setFeedback((current) => current ? { ...current, next_question_ready: true } : current);
        } else {
          timer = window.setTimeout(() => void checkNextQuestion(), 1000);
        }
      } catch (cause) {
        if (cancelled) return;
        setError((cause as Error).message);
        timer = window.setTimeout(() => void checkNextQuestion(), 1000);
      }
    }
    void checkNextQuestion();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [feedback?.next_question_ready]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!question) return;
    setLoading(true);
    setError("");
    try {
      const result = await api<Feedback>("/api/session/answer", {
        method: "POST",
        headers: sessionHeaders(),
        body: JSON.stringify({ question_id: question.id, answer }),
      });
      setFeedback(result);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section>
      <header><h1>{exercise.title}</h1></header>
      {loading && !question && <Message text="問題を生成しています…" kind="info" />}
      <Message text={error} />
      {!question && !loading && <button onClick={() => void loadQuestion()}>再試行</button>}
      {question && !feedback && (
        <form onSubmit={submit}>
          <div className="question-text"><MathText text={question.question_text} /></div>
          {question.answer_type === "number" ? (
            <label>解答<input inputMode="decimal" value={answer} onChange={(e) => setAnswer(e.target.value)} required autoFocus /></label>
          ) : (
            <fieldset>
              <legend>1つ選んでください</legend>
              {question.choices?.map((choice) => (
                <label className="choice" key={choice.id}>
                  <input type="radio" name="answer" value={choice.id} checked={answer === choice.id} onChange={(e) => setAnswer(e.target.value)} required />
                  {choice.label}
                </label>
              ))}
            </fieldset>
          )}
          <button type="submit" disabled={loading}>解答する</button>
        </form>
      )}
      {feedback && (
        <div className="feedback">
          <h2>{feedback.correct ? "正解" : "不正解"}</h2>
          <p>正答: <strong>{feedback.correct_answer_label}</strong></p>
          <dl>
            <div><dt>総解答数</dt><dd>{feedback.progress.total_answers}問</dd></div>
            <div><dt>直近の成績</dt><dd>{feedback.progress.recent_correct}/{feedback.progress.recent_answers}問正解（{feedback.progress.recent_accuracy_percent}%）</dd></div>
            <div><dt>目標</dt><dd>直近{feedback.progress.window_size}問で{feedback.progress.required_accuracy_percent}%以上</dd></div>
          </dl>
          {feedback.progress.achieved && <p className="achieved">目標を達成しました。続けて演習できます。</p>}
          <button
            onClick={() => void loadQuestion()}
            disabled={!feedback.next_question_ready}
          >
            {feedback.next_question_ready ? "次の問題" : "次の問題を生成中"}
          </button>
        </div>
      )}
    </section>
  );
}

export default function App() {
  const joinCode = new URLSearchParams(location.search).get("code") ?? "";
  const [exercise, setExercise] = useState<Exercise | null>(null);
  const [joined, setJoined] = useState(
    Boolean(sessionStorage.getItem("practiceHellToken")) &&
      sessionStorage.getItem("practiceHellJoinCode") === joinCode,
  );
  const [error, setError] = useState("");

  useEffect(() => {
    if (!joinCode) {
      setError("URLに参加コードがありません。教師から配布されたURLを開いてください。");
      return;
    }
    void api<Exercise>(`/api/exercises/${encodeURIComponent(joinCode)}`)
      .then(setExercise)
      .catch((cause: Error) => setError(cause.message));
  }, [joinCode]);

  return (
    <main>
      <div className="app-title">PracticeHell</div>
      <Message text={error} />
      {exercise && (joined ? <Practice exercise={exercise} /> : <AttendanceForm exercise={exercise} onJoined={() => setJoined(true)} />)}
    </main>
  );
}
