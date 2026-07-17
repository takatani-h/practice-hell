import { Fragment } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

const MATH_PATTERN = /(\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$\$[\s\S]*?\$\$|\$[^$]+\$)/g;
const KATEX_SETTINGS = { output: "html" } as const;

function Math({ block, math }: { block: boolean; math: string }) {
  const html = katex.renderToString(math, {
    ...KATEX_SETTINGS,
    displayMode: block,
    throwOnError: false,
  });

  return block
    ? <div dangerouslySetInnerHTML={{ __html: html }} />
    : <span dangerouslySetInnerHTML={{ __html: html }} />;
}

function normalizeGeneratedLatex(text: string) {
  // Structured output may occasionally contain JSON escaping twice. Only
  // collapse doubled backslashes when a doubled math delimiter proves that
  // the whole LaTeX fragment was escaped twice.
  if (text.includes("\\\\(") || text.includes("\\\\[")) {
    return text.replace(/\\\\/g, "\\");
  }
  return text;
}

export default function MathText({ text }: { text: string }) {
  const normalizedText = normalizeGeneratedLatex(text);

  return (
    <>
      {normalizedText.split(MATH_PATTERN).filter(Boolean).map((part, index) => {
        if (part.startsWith("\\[") && part.endsWith("\\]")) {
          return <Math key={index} block math={part.slice(2, -2)} />;
        }
        if (part.startsWith("\\(") && part.endsWith("\\)")) {
          return <Math key={index} block={false} math={part.slice(2, -2)} />;
        }
        if (part.startsWith("$$") && part.endsWith("$$")) {
          return <Math key={index} block math={part.slice(2, -2)} />;
        }
        if (part.startsWith("$") && part.endsWith("$")) {
          return <Math key={index} block={false} math={part.slice(1, -1)} />;
        }
        return <Fragment key={index}>{part}</Fragment>;
      })}
    </>
  );
}
