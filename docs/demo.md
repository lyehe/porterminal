# Demo: Give your agent any computer

Show an agent doing useful work on a computer while a human watches and joins
from a phone. The key moment is a label typed on the phone appearing in the
receipt that the agent reads back from the same terminal.

## The task

The [example project](../examples/agent-demo) is a tiny Python invoice tool
with an intentional discount bug. It uses only the standard library:

| File | Role |
|------|------|
| `invoice.py` | Applies a discount, currently with the wrong arithmetic |
| `checks.py` | Three checks; two fail before the fix |
| `receipt.py` | Asks for a label and prints the discounted total |
| `ptn.yaml` | A 48-column terminal and compose mode for phone recording |

The visible result goes from `FAILED (failures=2)` to three passing checks,
then to `Receipt launch-demo: $80.00` after the human enters `launch-demo`.

## Prepare a take

From a repository checkout, make a fresh copy for the agent to edit:

```bash
uv run --frozen python scripts/prepare_demo.py
```

The command prints an absolute path in your temporary directory. Change into
that folder so Porterminal loads the included recording preset:

```bash
cd "PATH_PRINTED_ABOVE"
uvx ptn
```

To record an unreleased checkout from the copied folder, replace `uvx ptn`
with `uv run --project "/path/to/porterminal" --frozen ptn`.
Run the normal mode so the agent and browser can share a terminal.
If the target shell uses `python3`, substitute it for `python` in the task.

Press **`c`** and paste the copied connection instructions into an agent
that supports remote MCP or HTTP requests. Add this task:

```text
Use this Porterminal computer for the task below, using one persistent
terminal session. Work in its starting directory.

1. Run python -B checks.py and inspect invoice.py.
2. Fix the discount bug in invoice.py. Leave the checks unchanged.
3. Run python -B checks.py again and confirm all three checks pass.
4. Run python -B receipt.py. Leave the "Receipt label:" prompt for me to
   answer from my phone; do not send an answer yourself.
5. After I enter the label, read the terminal screen and report the
   label and total printed by the receipt.

Use MCP if it is already available; otherwise follow the copied REST
instructions. Reuse the same shell/session throughout, and keep the
connection open while waiting for my input.
```

The `-B` flag keeps bytecode caches out of the demo, so a quick edit is picked
up immediately on the next run.

Scan the QR code on your phone, open the **🤖 tab**, and leave it visible.
At the label prompt, enter `launch-demo` and press Enter. With compose mode,
type the label and tap Send; it submits the text and Enter together. Ask the
agent to read the result if its chat is waiting for another message.

Each call to `prepare_demo.py` makes a new copy with the original bug, so
rehearsing and repeating takes leaves the source fixture intact. The starting
directory does not restrict the agent's access to the rest of the computer.

## A 60-second recording

Use a landscape frame with the agent chat on the left and a phone capture on
the right. Show the computer's Porterminal startup briefly at the beginning.
Keep the agent's connection and task readable, then give the shared terminal
most of the frame during the work.
Use a short shell prompt and check that the phone's text is readable at the
final video size before recording the full take. Agent sessions keep their
terminal dimensions when a browser joins, so the included narrow preset
prevents the phone from cropping a wide agent terminal.

| Time | What the viewer sees | Caption |
|------|----------------------|---------|
| 0–8s | `uvx ptn`, then the copied instructions pasted into the agent | Give your agent any computer |
| 8–15s | Phone opens the generated link and selects the 🤖 tab | One link. The same terminal. |
| 15–35s | Agent runs the failing checks, fixes the file, and reruns them; output appears on the phone | Your files. Your tools. Watch it work. |
| 35–50s | `Receipt label:` appears; the human types `launch-demo` from the phone | Join in from your phone |
| 50–60s | Receipt prints `$80.00`; agent reports the same label and total | Agent and human, one shared terminal |

The times are editing targets. Trim idle setup and waiting; caption sped-up
sections. Keep the phone input and resulting receipt at normal speed so the
shared interaction is easy to follow. Porterminal shares input; the agent
waits at the prompt because the task asks it to.

Use a scratch workspace and a fresh launch for each take. Stop Porterminal
after recording, and crop or mask the URL and QR code before publishing.

## README and launch assets

- **README loop:** 12–15 seconds showing failing checks, passing checks, and
  the phone answering the prompt. Keep text readable without sound.
- **Full demo:** the 45–60 second recording above, with captions and optional
  narration. Link it from the README loop or a static poster.
- **Export:** keep the loop around 960px wide, 10–15 fps, and preferably under
  5 MB. Use an absolute image URL when embedding it in the README so it also
  displays on PyPI.

The existing `assets/demo.gif` and `assets/demo.mp4` show the earlier phone
workflow. A fresh recording of the shared agent session should be the main
demo for this headline.

See [agent access](agent-access.md) for transport and session details.
