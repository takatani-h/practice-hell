import { render } from "@testing-library/react";
import { expect, it } from "vitest";
import MathText from "./MathText";

it("LaTeXの丸括弧と角括弧を数式として表示する", () => {
  const { container } = render(
    <MathText text={"文中の \\(x^2\\) と独立式 \\[y = 2x\\] を表示する。"} />,
  );

  expect(container.querySelectorAll(".katex")).toHaveLength(2);
  expect(container.querySelector(".katex-display")).not.toBeNull();
});
