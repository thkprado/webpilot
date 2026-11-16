// Service worker: `eval` through the debugger, and its error messages.

import { Args } from "./config";
import { answering } from "./scripts";
import { cdp } from "./cdp";

/** Message for a failed `eval`. Runtime errors already carry a stack trace; syntax errors only say
 * "Invalid or unexpected token", so they get the line, the column and an excerpt of the source with
 * a caret under the offending character. Line breaks and tabs in the excerpt are shown as ⏎ and ⇥,
 * so the excerpt stays on one line and the caret lines up. */
function evalError(source: string, details: any, isFunction: boolean): string {
  const message = details.exception?.description || details.text || "evaluation failed";
  if (details.exception?.className !== "SyntaxError" || typeof details.lineNumber !== "number") return message;
  const line = details.lineNumber;
  // Runtime.callFunctionOn compiles the declaration inside parentheses: one extra column on line 0.
  const column = Math.max(0, (details.columnNumber ?? 0) - (isFunction && line === 0 ? 1 : 0));
  const lines = source.split("\n");
  if (line >= lines.length) return message;
  let offset = column;
  for (let i = 0; i < line; i++) offset += lines[i].length + 1;
  const start = Math.max(0, offset - 40);
  const end = Math.min(source.length, offset + 30);
  const visible = (s: string) => s.replace(/\n/g, "⏎").replace(/\t/g, "⇥").replace(/\r/g, "␍");
  const excerpt = (start > 0 ? "…" : "") + visible(source.slice(start, end)) + (end < source.length ? "…" : "");
  const caret = " ".repeat((start > 0 ? 1 : 0) + offset - start) + "^";
  return `${message} at line ${line + 1}, column ${column + 1}:\n  ${excerpt}\n  ${caret}`;
}

/** `eval`: the expression's value in the tab's main frame, through the debugger (so CSP does not apply). */
export async function evaluate(tabId: number, a: Args) {
  const source = String(a.expression);
  let r;
  if (Array.isArray(a.args)) {
    // The expression is a function; the arguments travel as JSON values, never as code.
    const global = await answering(tabId, [0], cdp(tabId, "Runtime.evaluate", { expression: "globalThis" }));
    try {
      r = await answering(tabId, [0], cdp(tabId, "Runtime.callFunctionOn", {
        functionDeclaration: source, objectId: global.result.objectId,
        arguments: a.args.map((value: unknown) => ({ value })),
        returnByValue: true, awaitPromise: true, userGesture: true,
      }));
    } catch (e: any) {
      if (String(e?.message).includes("does not evaluate to a function")) {
        throw new Error("with arguments, the expression must be a function, such as (text, n) => ...");
      }
      throw e;
    }
  } else {
    r = await answering(tabId, [0], cdp(tabId, "Runtime.evaluate", {
      expression: source, returnByValue: true, awaitPromise: true, userGesture: true,
    }));
  }
  if (r.exceptionDetails) throw new Error(evalError(source, r.exceptionDetails, Array.isArray(a.args)));
  if (!Array.isArray(a.args) && r.result?.type === "function") {
    // A bare function would come back as {}: say so instead of returning a value that looks like data.
    throw new Error("the expression is a function, which eval returns without calling it: call it, "
      + "(() => ...)(), or pass its arguments (--arg, or args=[...] in Python; args=[] for none)");
  }
  return r.result?.value ?? null;
}
