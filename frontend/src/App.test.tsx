import { render, screen } from "@testing-library/react";
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
