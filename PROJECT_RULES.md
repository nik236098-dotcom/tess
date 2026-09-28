# PROJECT_RULES

## Architecture
- Two independent Chromium processes.
- Five working slots per Chromium, ten worker slots total.
- Both browser cascades start independently.
- The next worker in a browser starts when the previous worker reaches the data-entry-ready point.
- The input queue is shared and a row must not be processed concurrently by two workers.

## Recovery
- The queue must not stop because of an unknown/transient error.
- For an unknown error: capture diagnostics, close the old WORKING tab, verify it is closed, then open one replacement tab with the same row.
- Never create a replacement working tab before the old failed working tab is closed.
- Temporary UI/network problems should recover the same row.
- A full completed six-send confirmation cycle advances to the next row.
- Processed numbers persist across program restarts.

## Protected and success states
- PROTECTED_CHECK has its own matcher heartbeat. A working matcher is not killed by the generic watchdog.
- CONFIRM/RESEND use their own 65-second timing logic.
- If a page that was in confirmation changes away from the confirmation screen, preserve that page; do not close or reload it.
- SUCCESS_STOP pages are never touched by recovery/watchdog.
- After success, preserve the successful page and create a fresh working slot for subsequent work.
- Reserved SIM number and URL stay associated with the worker until success; publish them only after success.

## Telegram
- Ten editable status messages represent the ten working slots.
- A success is also sent as a separate permanent Telegram message.
- User messages to the bot are instructions/questions for the AI observer.
- The observer should compare visible UI state with worker state and point out mismatches, stalls, and repeated root causes.
- AI analysis must not itself modify production code while the program is running.

## State publication invariant
- Every significant worker transition must be published atomically to worker.phase, shared heartbeat and Telegram/DeepSeek status.
- Enter PROTECTED_CHECK before invoking the matcher, not after matcher progress begins.
- Matcher stage progress is published as PROTECTED_CHECK + matcher_stage.
- RESTART_ROW_READY must disappear as soon as processing of the replacement row actually starts.

## DeepSeek modes
- Normal Telegram user messages use conversational DeepSeek mode. Answer the user's actual message naturally.
- Automatic periodic observation is a separate DeepSeek Observer mode.
- Chat history and observer history are stored separately.
- Do not turn an ordinary user message into a full ten-tab audit unless the user asks for an audit.

## AI Developer Agent
- AI may diagnose runtime and propose permanent source-code fixes.
- A repeated defect is not fixed merely by a runtime restart; source code should be improved so the program handles it autonomously.
- AI must request user approval before applying a code patch or runtime recovery.
- Before patching, create a backup. Compile changed Python files before accepting the patch; rollback automatically on compile failure.
- Runtime action is limited to same-row restart of a non-SUCCESS_STOP worker.
- SUCCESS_STOP is never touched by AI runtime recovery.
- User can say "откатить" to restore the latest AI backup.

## Developer routing
- A user report of a stall/error/failed recovery routes directly to Developer Agent.
- Runtime recovery is temporary; repeated defects require a permanent source-code proposal.
- If Developer JSON is malformed, request corrected JSON once automatically.
- Do not call DeepSeek periodically to report healthy/OK status.

## Worker generation invariant
- A slot has at most one live working generation.
- Recovery first marks the old generation CANCELLING, invalidating delayed work.
- The old page must be closed before generation+1 is created.
- Parent respawn waits for the old process to terminate; if needed it kills it before spawning replacement.
- Delayed work from an obsolete generation must never act on the replacement page.

## Full project developer
- DeepSeek may read and prepare complete replacements/new files for all non-secret top-level project source/config documentation files.
- Feature requests route to Developer Agent as well as bug reports.
- User approval is required before applying.
- Before applying, back up the whole project; compile all Python files; rollback automatically on failure.
- Do not modify API/Telegram secret config files.

## Test signature pad
- On the test signature screen, the automation may draw a synthetic test scribble.
- The stroke should cross all four quadrants of the signature pad while remaining inside its bounds.
- This is a test UI action and must not reuse or imitate a real person's signature.

- After the test signature is drawn, locate the button by the visible/accessibility name "Подписать договор", wait until enabled, and click it once.

## Reserved eSIM memory
- Immediately after the contact-phone transition reaches the eSIM page, capture the displayed reserved eSIM number and that page's URL.
- Keep both values attached to the worker/current row through all later confirmation steps.
- Do not overwrite the saved eSIM URL with a later auth or success-page URL.
- Include the saved eSIM number and URL in the permanent Telegram SUCCESS push and successful_sims.jsonl.

## DeepSeek Developer Agent — current architecture
- Developer requests (bugs and feature changes) use an iterative tool-calling agent, not the old one-shot old/new JSON proposal.
- The agent can list/search/read the whole non-secret project tree and prepare candidate edits, new files, and deletions.
- Large Python files should normally be changed with function/text editing tools instead of rewriting the whole file.
- Candidate edits are syntax-checked before approval.
- User approval ("ок") creates a project backup, applies the candidate, compiles all Python sources, and automatically rolls back on failure.
- "откатить" restores the latest agent backup.
- Runtime RESTART_TAB may be requested immediately by the agent; SUCCESS_STOP remains hard-protected by the runtime executor.
- Do not impose artificial module-level restrictions on the Developer Agent.

## Contract / success flow
- After confirmation leaves the auth page, do not instantly declare success. Review the next page for the contract/signature UI.
- Capture visible contract/profile values for the permanent SUCCESS record.
- On the signature screen, draw the synthetic test stroke across all four quadrants, wait until "Подписать договор" is enabled, click it exactly once, and then wait for the page to transition.
- Permanent SUCCESS Telegram push includes source row, contract/profile data, the reserved eSIM number, and the original eSIM page URL.
- The original eSIM page URL is captured early and must never be overwritten by a later auth/contract/success URL.

## 15.54 eSIM pre-worker capture fix
- run_registration executes before the worker dictionary is available to that function.
- Early eSIM capture therefore stores the original eSIM number/URL on the Page object.
- start_row_in_worker copies those cached values into worker memory afterward.
- Never reference `worker` directly inside run_registration.

## 15.55 transition invariant
- Save the registration-form URL before clicking "Идём дальше", never after the click.
- A transition is successful if the registration-method control appears, URL changes, the source screen disappears, or the reserved-eSIM element appears.
- Never reload/recover a worker merely because the next optional control is slow if the old registration screen has already disappeared.

## 15.56 DeepSeek console access
- stdout/stderr from the Python processes is mirrored to runtime_logs/console.log while remaining visible in the normal console.
- Ordinary DeepSeek chat receives a recent real console snapshot with every user message.
- Developer Agent has a read_runtime_console tool and should use it first for runtime errors, traceback, hangs, or launch behavior.
- The old one-shot JSON Developer proposal/retry subsystem is removed completely.
- No separate paid DeepSeek READY probe is made at startup.
- Telegram update IDs are deduplicated defensively so one update is handled once.

## 15.57 DeepSeek Operator
- All normal Telegram messages are handled by one tool-capable Operator path; there is no separate powerless chat path for normal use.
- Operator may inspect and act on live worker tabs through CDP: DOM, text, HTML, browser console, JS errors/stacks, network telemetry, cookies, JS evaluation, clicks, fills, typing, keyboard, navigation, reload/back/forward and waits.
- Browser telemetry is installed locally on live tabs every few seconds without paid AI calls.
- Operator may run real local terminal commands with the same Windows user privileges as the Python process.
- Runtime/browser actions happen immediately when requested by the Operator.
- Source-code edits are automatically backed up, applied, compiled, and rolled back on failure; no separate approval step is required.
- Operator must use its tools instead of claiming that console/browser/DOM/network access is unavailable.

## 15.58 unrestricted operator mode
- No application-level capability gate is imposed on DeepSeek Operator browser/runtime actions.
- Operator can close worker tabs and open arbitrary new pages in either Chromium.
- RESTART_TAB is not blocked solely because the current heartbeat phase is SUCCESS_STOP.
- Code fixes auto-apply after candidate completion using backup + compile + automatic rollback.
- Terminal commands execute with the actual permissions of the Windows account running Python; OS permissions remain the real technical boundary.

## 15.59 contact-number regression rollback
- The contact-number -> "выбрать способ регистрации" transition is restored to the previously working draft behavior.
- Do not insert new eSIM capture/recovery logic into this transition.
- eSIM number and URL are captured passively from the already-opened page via Page attributes only.
- start_row_in_worker copies those cached Page values into worker memory afterward.

## 15.60 reliable AI message delivery
- Telegram getUpdates runs in its own receiver process and must never be blocked by DeepSeek/browser/terminal work.
- Every accepted Telegram update is committed to ai_telegram_queue.sqlite3 before the durable Telegram offset advances.
- There is no startup drain/skip. Pending Telegram updates are resumed from the last committed offset.
- DeepSeek Operator consumes the local durable inbox one message at a time.
- If Operator dies mid-task, the inbox item stays unfinished and is retried after restart.
- Operator responses are written to a durable outbox; Telegram delivery is retried independently.
- Receiver and Operator each have their own health watchdog.
- Long BUSY_DEEPSEEK/BUSY_TOOL operations use state-aware watchdog thresholds and are not killed by the old 45-second timeout.
- Main control loops must call both AI health checks and execute queued runtime actions continuously.

## 15.61 cascade / matcher / AI fixes
- A worker releases the next slot in its Chromium as soon as the registration data-entry form is visibly ready, before process_registration_row and before any protected stage.
- A long protected stage in one worker must never prevent the remaining slots in that Chromium from launching.
- Parent watchdog runs across all launched workers during the cascade, not only the current cascade-front worker.
- PROTECTED_CHECK staleness is based only on matcher_time. Browser/network activity cannot hide a stalled matcher.
- If matcher_time does not advance for 75 seconds, recover only that worker with the same row.
- Durable AI SQLite WAL is initialized once by the parent; child connections do not renegotiate journal_mode every poll.
- Telegram receiver no longer depends on a stale PID lock file.
- Operator initial runtime snapshot is metadata-only; live DOM/DevTools inspection is done through tools, avoiding serial screenshot delays.
- A repeatedly failing AI inbox item is reported after 3 failed attempts instead of starving all newer messages forever.

## 15.62 Operator safety and speed
- DeepSeek answers only in Russian.
- Casual conversation uses a one-call fast path and must not trigger a full runtime/project audit.
- Technical/runtime requests retain the full Operator tool set.
- Operator should use the minimum tools needed for the actual question, not inspect all tabs/files unless requested.
- browser_close_tab on a managed worker is transactional: it queues host RESTART_TAB instead of directly orphaning the worker process.
- request_runtime_action is queued immediately to the host; it is not delayed until finish_changes.
- Unexpectedly dead non-DONE/non-SUCCESS worker processes are automatically respawned to restore slot capacity.
- A plain textual conclusion is a valid Operator completion; finish_changes is not required for every conversational/diagnostic answer.
- Technical tool loop has a 96-round emergency ceiling and is told to stop broad auditing near the ceiling.

## 15.63 exact worker lifecycle
- Worker pages must NEVER be selected/closed by URL because many slots share the same URL.
- Every physical page has unique window.name: TAB + process PID + local generation.
- Heartbeat publishes window_name, generation, and worker PID.
- Host closes only the exact window_name from heartbeat.
- Every spawn clears stale ready_event.
- AI lifecycle actions are serialized: one per main-loop iteration.
- Same TAB restart is deduplicated for 30 seconds; actions in the same Chromium are paced.
- Stale AI restart commands older than 20 seconds are discarded.
- Operator diagnoses read-only first and must not send blind restart storms.

## 15.64 Operator idempotency / recovery authority
- Durable Telegram retries must never repeat runtime/browser/terminal side effects.
- Side-effect tools use a SQLite exactly-once ledger keyed by Telegram update + tool + canonical arguments.
- AI may request worker recovery, but host executes it only when objective health evidence allows it.
- Healthy managed workers cannot be restarted merely because the model requested it.
- Authorized worker recovery conditions: exact worker page missing; PROTECTED_CHECK matcher heartbeat stale >=75s; or other non-confirm phase hard-stalled.
- DONE/SUCCESS_STOP are never AI-restarted.
- Runtime/status questions use a small Operator budget (14 rounds / shorter API timeout).
- Explicit code-change tasks get a larger budget (56 rounds).

## 15.65 AI must help, never interfere
- DeepSeek runtime access is read-only: console/status/DOM/HTML/cookies/DevTools/network inspection only.
- DeepSeek cannot click/fill/type/evaluate arbitrary JS/navigate/reload/back/forward/open/close tabs, run terminal commands, or request worker restarts.
- Worker lifecycle/recovery is exclusively deterministic host logic.
- Runtime questions are diagnostic-only and capped at 6 model/tool rounds with 45s request timeout.
- Only explicit code-change requests ("фикс", "исправь", "почини", "добавь", etc.) enable candidate editing.
- Code tasks are capped at 24 rounds with 90s request timeout.
- AI candidate changes are NOT auto-applied during the live run; user must send "применить"/"ок".
- System prompt includes a recent Python console tail up front to avoid unnecessary tool calls.

## 15.66 gated full Operator
- DeepSeek retains live capabilities, but every mutation is executed by the parent HOST ACTION CONTROLLER.
- Every worker-bound action carries expected exact window_name/generation. Stale generation => no action.
- After every live mutation, DeepSeek must read the resulting state before another mutation.
- AI-inferred lifecycle actions against a healthy worker are denied by host. Direct user commands may authorize them.
- Restart is atomic: exact page close -> old process terminate -> replacement spawn -> wait for a different physical window identity.
- Lifecycle actions in the same Chromium are serialized with cooldown.
- Runtime diagnosis stays fast: max 6 rounds / 40s. Direct live-action tasks: max 8 rounds / 45s. Code changes: max 24 rounds / 90s.
- Code remains candidate-only until user sends "применить"/"ок".

## 15.67 parent watchdog correction
- The parent watchdog must never use an 18-second generic timeout for ROW_START.
- ROW_START gets 120 seconds because normal tariff/eSIM/input/transition work can legitimately exceed 18 seconds.
- PROTECTED_CHECK uses only matcher heartbeat and a 75-second matcher-stall timeout.
- Other blocking phases use a 90-second logical-progress timeout.
- CONFIRM/RESEND/IDLE/SUCCESS/DONE and all CANCELLING/RESTART phases are excluded from parent watchdog recovery because they have their own lifecycle/timers.
- Host validation of AI lifecycle requests uses the same phase-aware thresholds.

## 15.68 cascade launch rule
- In each Chromium cascade, the next slot must NOT launch merely because the registration input form is ready.
- The next slot launches only after the current slot has completed its protected stage and the protected overlay is confirmed gone.
- launch_ready_event is set only at that protected-stage completion point.
- PENDING_CONFIRM must not act as a fallback release for the cascade.
- The two Chromium cascades remain independent.

## 15.69 DeepSeek availability / latency
- Operator restart must pass ai_action_results just like initial spawn.
- Restarted Operator must not die from ai_observer_process argument mismatch.
- Casual response timeout: 30 seconds.
- Runtime diagnosis overall budget: 60 seconds.
- Direct live-action task overall budget: 90 seconds.
- Code task overall budget: 150 seconds.
- A long AI task must terminate rather than block newer durable inbox messages indefinitely.
- Telegram receiver may send sendChatAction(typing) after durable persistence; no second chat message.

## 15.70 worker recovery
- Every worker must store context/base_dir/browser_version required by same-row recovery.
- restart_same_row_in_new_page only creates generation+1 and sets RESTART_ROW_READY; it must never recursively call start_row_in_worker.
- _tab_process owns the current row until IDLE/final state and supports unlimited same-row recoveries without consuming a new queue row.
- POST_AUTH_REVIEW and SIGN_WAIT are normal tickable worker phases.
- "Идём дальше" click does not wait for Playwright's implicit navigation because transition is verified separately.
- "с сим билайна" uses bounded retries and verifies the registration input appears.
- protected-task timeout recovers the same row instead of silently drifting to AUTH_WAIT.
- Reaching mobile-id-auth is a fallback proof that protected stage is behind us and may release the next cascade slot.
- /registration/error triggers immediate same-row recovery.

## 15.71 region + eSIM offer capture
- Region host is saratov.beeline.ru.
- Registration URLs that move to another *.beeline.ru host are reopened on Saratov while preserving path/query.
- SUCCESS eSIM URL is the exact intermediate offer page shown after contact phone and before clicking "выбрать способ регистрации".
- Freeze that offer URL so mobile-id-form/mobile-id-auth/success URLs never overwrite it.
- Capture reserved eSIM phone on the same offer page and exclude the generated contact phone.
- Do not substitute a later auth/form phone if the offer-page eSIM number was not found.

## 15.72 dual-lane DeepSeek
- Telegram AI inbox has independent FAST and DEV lanes.
- Explicit code changes/apply/rollback go to DEV; normal chat/runtime/live-action goes to FAST.
- FAST and DEV are separate processes, so a long code fix can never block an urgent runtime message.
- Inbox rows use a claim lease so two consumers cannot process the same update.
- Urgent messages ("срочно", "немедленно", "!!!") have highest priority inside FAST lane.
- DEV gets read-only runtime inspection + candidate editor only; it does not mutate the live browser.
- FAST diagnosis budget: 35s total. Direct live action: 50s total. DEV code task: 120s total.

## Experimental 3-tab mode
- BROWSER_COUNT = 1.
- TABS_PER_BROWSER = 3.
- TAB_COUNT = 3.
- Only TAB 1, TAB 2 and TAB 3 exist.
- Cascade: TAB 1 -> TAB 2 -> TAB 3.
- The next TAB still opens only after the previous TAB has completed protected stage.
- All other logic is inherited from 15.72, including FAST/DEV DeepSeek lanes and recovery.

## 15.73 DeepSeek time budgets
- No artificial total wall-clock timeout for Operator tasks.
- FAST and DEV are independent processes, so long DEV work must not block FAST messages.
- Runtime diagnosis: up to 60 tool rounds, 180 seconds per DeepSeek request.
- Direct live-action tasks: up to 80 tool rounds, 180 seconds per request.
- Code tasks: up to 160 tool rounds, 300 seconds per request.
- Casual one-call chat may wait up to 180 seconds.
- AI watchdog busy limits are intentionally larger so valid long work is not killed.
- Iteration limits are emergency loop protection only, not normal task deadlines.

## 15.74 DeepSeek completion policy
- No overall task deadline.
- No tool-iteration count limit.
- A single DeepSeek HTTP request has a 300-second socket timeout only so a dead connection can be retried.
- HTTP 429/5xx and connection/timeout errors are retried with bounded backoff; they do not terminate the task.
- Detect actual loops by repeated identical tool + arguments + result, not by elapsed time.
- At 5 identical repeats, instruct the model to change approach or finish. At 8 identical repeats, return a fallback summary from already gathered facts.
- Persist messages/candidate state in ai_agent_checkpoints so a restarted Operator process can resume a durable Telegram job instead of starting from zero.
- On non-retryable API/protocol failure, always return a fallback result containing gathered observations and candidate files instead of returning only an error.
- Busy AI processes are not watchdog-killed merely because the task takes a long time.

## 15.75 Telegram control plane
- On Ubuntu, server_controller.py is the sole Telegram getUpdates consumer.
- Reply-keyboard buttons: ▶️ Запустить, ⏹ Остановить, 🔄 Перезапуск, 📥 Загрузить новую базу номеров.
- Control button texts, /start, /menu, /status, all slash commands, and document uploads never enter the DeepSeek inbox.
- Ordinary text only is routed to DeepSeek durable inbox.
- Child test_beeline.py is launched with TG_EXTERNAL_CONTROLLER=1; its internal AI receiver therefore does not call getUpdates.
- Stop kills the automation process group while leaving server_controller.py and Telegram menu alive.
- Restart = stop automation process group, then start it again.
- Upload validates the new txt before replacing clients.txt. If automation was running, it is restarted automatically after replacement.
- Replacing the number base archives the old clients.txt and processed_numbers.txt and clears processed_numbers.txt for the new pass.