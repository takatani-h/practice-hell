import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

describe("App", () => {
  beforeEach(() => {
    location.hash = "";
    sessionStorage.clear();
    vi.stubGlobal("fetch", vi.fn());
  });

  it("参加フォームを表示する", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "演習に参加" })).toBeInTheDocument();
    expect(screen.getByLabelText("参加コード")).toBeInTheDocument();
    expect(screen.getByLabelText("表示名")).toBeInTheDocument();
  });
});
