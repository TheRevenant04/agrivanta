import { appendFileSync } from "fs"
import { join } from "path"

const DENIED = [
  /^git\s+push\s+(--force\b|-f\b)/,
  /^git\s+reset\s+--hard/,
  /^git\s+clean\b/,
  /^git\s+commit\s+--amend/,
  /^git\s+rebase\b/,
  /^rm\s+-rf\b/,
]

export const Guardrails = async ({ directory }) => {
  const logPath = join(directory, ".opencode", "guardrails.log")

  const log = (entry) => {
    try {
      appendFileSync(logPath, `${new Date().toISOString()} ${entry}\n`)
    } catch {
      // audit logging must never break the session
    }
  }

  return {
    "tool.execute.before": async (input, output) => {
      if (input.tool === "bash") {
        const command = String(output.args?.command ?? "").trim()
        log(`bash: ${command}`)
        for (const pattern of DENIED) {
          if (pattern.test(command)) {
            throw new Error(
              `Blocked by guardrails: "${command}" violates _docs/permissions.md. Ask a human to run it if it is truly needed.`,
            )
          }
        }
      }
      if (input.tool === "edit" || input.tool === "write" || input.tool === "patch") {
        log(`${input.tool}: ${output.args?.filePath ?? output.args?.path ?? "?"}`)
      }
    },
  }
}
