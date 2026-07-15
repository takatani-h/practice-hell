import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import App from "./App";

beforeEach(() => {
  history.replaceState({}, "", "/");
  sessionStorage.clear();
  vi.stubGlobal("fetch", vi.fn());
});

it("参加コードがない場合に案内を表示する", () => {
  render(<App />);
  expect(screen.getByText(/URLに参加コードがありません/)).toBeInTheDocument();
});

it("次問の生成中は次へ進むボタンを無効にする", async () => {
  history.replaceState({}, "", "/?code=test-simple-addition");
  sessionStorage.setItem("practiceHellToken", "test-token");
  sessionStorage.setItem("practiceHellJoinCode", "test-simple-addition");
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
    const path = String(input);
    if (path.startsWith("/api/exercises/")) {
      return Response.json({
        join_code: "test-simple-addition",
        title: "単純な足し算",
        answer_type: "number",
        mastery: { window_size: 5, required_accuracy_percent: 100 },
      });
    }
    if (path === "/api/session/question") {
      return Response.json({
        id: 1,
        question_text: "\\(2 + 2\\) を計算してください。",
        answer_type: "number",
      });
    }
    if (path === "/api/session/answer" && options?.method === "POST") {
      return Response.json({
        correct: true,
        correct_answer: "4",
        correct_answer_label: "4",
        progress: {
          total_answers: 1,
          recent_answers: 1,
          recent_correct: 1,
          recent_accuracy_percent: 100,
          window_size: 5,
          required_accuracy_percent: 100,
          achieved: false,
        },
        next_question_ready: false,
      });
    }
    if (path === "/api/session/question-status") {
      return Response.json({ ready: false });
    }
    return Response.json({ detail: "not found" }, { status: 404 });
  }));

  render(<App />);
  fireEvent.change(await screen.findByLabelText("解答"), { target: { value: "4" } });
  fireEvent.click(screen.getByRole("button", { name: "解答する" }));

  const nextButton = await screen.findByRole("button", { name: "次の問題を生成中" });
  expect(nextButton).toBeDisabled();
});
