import { Fragment } from "react";
import { BlockMath, InlineMath } from "react-katex";
import "katex/dist/katex.min.css";

const MATH_PATTERN = /(\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$\$[\s\S]*?\$\$|\$[^$]+\$)/g;

export default function MathText({ text }: { text: string }) {
  return (
    <>
      {text.split(MATH_PATTERN).filter(Boolean).map((part, index) => {
        if (part.startsWith("\\[") && part.endsWith("\\]")) {
          return <BlockMath key={index} math={part.slice(2, -2)} />;
        }
        if (part.startsWith("\\(") && part.endsWith("\\)")) {
          return <InlineMath key={index} math={part.slice(2, -2)} />;
        }
        if (part.startsWith("$$") && part.endsWith("$$")) {
          return <BlockMath key={index} math={part.slice(2, -2)} />;
        }
        if (part.startsWith("$") && part.endsWith("$")) {
          return <InlineMath key={index} math={part.slice(1, -1)} />;
        }
        return <Fragment key={index}>{part}</Fragment>;
      })}
    </>
  );
}
