# How the vehicle assistant handles invalid requests and failures

The most important change is what happens when a reply fails halfway through. Previously, the assistant could remember part of a failed exchange, and pressing **Retry** could add the same question twice. The API now starts from the last completed conversation and saves the next exchange only after it has a valid reply. It also keeps a record of each request so it can recover when the server finishes a reply but the browser loses the connection.

In this guide, a **session** is one browser conversation and its daily allowance. A **turn** is one question and the assistant’s attempt to answer it. A turn can involve several calls to the AI model or inventory tools.

## 1. Invalid chat messages and search filters

The browser already blocked a blank message, but someone calling the API directly could send spaces and use one of their seven calls. Some input fields also accepted unintended values. For example, the string `"yes"` could turn on a conversation reset, and a misspelled search field could silently leave a filter out.

| Input | What happens now |
|---|---|
| A chat message containing only spaces | The API trims the message, returns HTTP 422 with validation details, and leaves the session allowance available. A valid message contains 1–2,000 characters after trimming. |
| `"reset_context": "yes"` or an unknown chat field | The API rejects the request. The reset flag accepts the JSON values `true` and `false`. |
| A search tool receives `"max_price": "900000"` or `"min_price": true` | Search validation rejects these values. Prices must be whole, nonnegative numbers, and the minimum must be at most the maximum. The same checks apply when code calls the vehicle service directly. |
| A brand such as `" Honda "` | The service searches for `Honda`. Blank filter text, unknown search fields, and text exceeding the field’s catalogue limit are rejected. |
| Vehicle ID `0`, `true`, or a positive integer above 2,147,483,647 | Validation stops the lookup before it reaches the database. A valid ID with no matching row produces the ordinary “Vehicle not found” result. |

These search rules apply to the structured inputs the assistant sends to its tools. Customers can still type a natural-language question such as “Show me Hondas under 9 lakh.” EMI calculations already checked loan amount, rate, and duration at both the tool and service boundaries. [Chat request schema](../app/api/schemas.py) · [Search rules](../app/models/SearchRequest.py) · [Vehicle service](../app/services/vehicle_service.py) · [EMI rules](../app/models/emi.py)

## 2. Session ownership and conversation resets

Previously, the client could choose a session ID. The server used that ID to select both history and usage. Someone who knew the ID could continue the conversation, and choosing another ID could open another session budget.

On the first request, the client omits `session_id`. The server issues a random ID and sets a separate ownership cookie. The browser sends that cookie on later chat and usage requests. A script using the API needs to retain the cookie between calls. An unknown session or a missing or mismatched owner receives HTTP 404 with the code `session-expired`. Omitting the ID again while retaining a valid ownership cookie resumes the owned session.

**Reset conversation** starts the assistant with fresh context on the next turn. The daily allowance stays attached to the session. This is an anonymous, browser-based ownership check. Per-IP limits also apply, including when a browser starts over after clearing cookies. [Session ownership and budgets](../app/api/chat_usage.py) · [Browser client](../frontend/src/api/client.ts)

## 3. Failed replies, retries, and two requests at once

Previously, the model could save the user’s question and an unfinished tool call before the turn failed. The browser removed the failed exchange when retrying, but the model could still see it. Two tabs could also start work on the same history at the same time.

The browser now gives each new turn a `request_id` and reuses it when the user presses **Retry**. SQLite stores a request record, reserves the session while the turn runs, and saves the completed history and reply together. Both chat endpoints use this record.

| What went wrong | How the assistant responds now |
|---|---|
| Inventory processing or generation failed before a reply was saved | Retrying the latest turn with its original ID uses the last completed history and shares the original session charge. The question appears once in the successful history. |
| The server saved the reply, then the browser lost the connection | With the same session, request ID, message, and reset setting, the API returns the saved reply. It skips generation and adds no session charge. |
| The user stopped a stream | The browser marks the attempt as cancelled. The server cleans up active stream work. If the reply was already committed when the connection closed, the saved reply is available on retry. |
| A second tab sends a new question while a reply is in progress | The API returns HTTP 409 and asks the caller to try again shortly. The first turn continues. A time limit on the reservation allows recovery if a worker stops unexpectedly. |
| A caller reuses an ID for different text, changes its reset flag, or retries an unfinished turn after a newer one began | The API returns HTTP 409. A changed or superseded question needs a new request ID. |

For example, suppose a user asks for Honda sedans and the connection drops after the answer was saved. Pressing **Retry** retrieves that answer. Typing the question again as a new message creates a new turn and uses another session call. Both HTTP attempts are subject to the IP rate limit. [Turn handling](../app/api/routes/chat.py) · [Request records](../app/api/chat_usage.py) · [Browser retry handling](../frontend/src/hooks/useChat.ts)

## 4. Startup failures, database outages, and readiness

Previously, agent initialization and the SQLite usage check ran outside the chat error handler. Missing configuration or an inaccessible usage file could produce a plain-text HTTP 500 before the first stream event. An inventory query failure could also end the entire conversation turn with a generic message.

| Failure or check | Current behavior |
|---|---|
| Chat cannot initialize, for example because the provider key is missing | Chat returns HTTP 503 with a short JSON error message. The server logs the initialization failure type. |
| SQLite cannot record the request | The API returns HTTP 503 with “Conversation storage is temporarily unavailable.” Generation starts only after the request has been recorded. |
| PostgreSQL fails during a vehicle search or detail lookup | The tool reports “Inventory is temporarily unavailable.” The assistant can explain the outage and continue with parts of the question that do not require inventory. The exact final wording depends on the model. |
| An operator checks whether the API process responds | `GET /api/health` provides a lightweight liveness check. A successful response here only confirms that the API can answer that check. |
| An operator checks whether chat dependencies are ready | `GET /api/ready` checks agent initialization, access to the expected inventory columns, provider key access, and a SQLite write that it rolls back. It returns HTTP 503 for an unavailable dependency. `GET /api/health/services` gives separate results for the API, database, and provider. |

The readiness check verifies provider access without generating a model reply. A later model request can still fail. [Agent initialization](../app/api/dependencies.py) · [Health and readiness](../app/api/routes/health.py) · [Inventory tools](../app/tools/agent_tools.py)

## 5. Slow requests and timeouts

Previously, the streaming route waited for SQLite on the same thread that served other asynchronous requests. Even reading usage acquired a write lock. A stuck generation could keep the browser waiting because each stream heartbeat restarted its inactivity timer.

Chat now runs SQLite work off the event loop, and ordinary usage reads no longer start a write transaction. A heartbeat still tells the browser that a connection is alive, but it cannot extend the overall deadline.

| What is waiting | Configured limit |
|---|---|
| SQLite waiting for a lock | 2 seconds |
| Inventory database connection, connection-pool wait, and SQL statement | 4 seconds to connect, 5 seconds for the pool, 8 seconds for a statement |
| Individual model request | 30 seconds, with automatic provider retries disabled in the model client |
| Server-side chat generation | 100 seconds |
| Browser receiving a chat reply | 60 seconds of inactivity and a 120-second overall deadline |

When the server’s generation deadline expires, it reports a timeout with status 504. If streaming has already started, that status travels inside the final error event. The browser also surfaces a timeout if its own deadline expires first. [Database configuration](../app/database.py) · [Model configuration](../app/agents/agent.py) · [Stream handling](../app/api/routes/chat.py) · [Browser timers](../frontend/src/api/client.ts)

## 6. Three different reasons for a limit message

Previously, error handling looked for particular words in exception messages. The browser could show a 60-second IP cooldown after a user exhausted a 24-hour session allowance. It could also leave the message box disabled after the allowance renewed.

| Error code | What it means | What the user can do |
|---|---|---|
| `ip-rate-limit` | The configured request limit for this IP address was reached. | Wait for the interval in `Retry-After`. The browser uses 60 seconds as a fallback if the interval is missing. |
| `session-limit` | The session used its seven calls in its 24-hour window. | Wait for the displayed renewal time. The browser uses the server’s retry interval and clears the exhausted state at renewal. |
| `conversation-limit` | This particular question reached the agent’s processing limit of five model calls. | Send a simpler question. The limit applies to the work needed for one turn. |

The API recognizes the model limit by its exception type. For HTTP errors it sends the limit category in `X-Error-Code`. During an open stream it can send the category in the terminal error event. [IP rate handling](../app/api/rate_limit.py) · [Chat error mapping](../app/api/routes/chat.py) · [Browser error mapping](../frontend/src/api/client.ts)

## 7. Invalid replies and interrupted streams

Previously, an empty agent result could appear as a successful fallback reply. Malformed message content could cause a generic 500. The browser also trusted the shape of a `completed` event, so it could mark a request successful even when the reply field was missing.

The API now checks the final message and requires nonblank assistant text. An incomplete result produces a 502 error. The browser checks session IDs, progress fields, text updates, error details, and the completed reply before using them. Invalid event data produces a server-response error. A connection that closes before a terminal event produces an interrupted-connection error.

**Reading a streaming response:** Before the stream opens, a client can read the HTTP status and JSON error body. Once the stream opens, the HTTP headers have already been sent. The client must read until it receives either `completed` or `error`. Receiving partial text alone does not establish that the reply finished. [Reply validation and stream events](../app/api/routes/chat.py) · [Browser stream reader](../frontend/src/api/client.ts)

## 8. Browser storage and server restarts

Previously, the browser could parse saved JSON successfully and then crash because the data had the wrong shape. Storage write failures were silent. After a server restart, the browser could display earlier messages even though the assistant had lost the context needed to understand “the second car.”

The browser now checks saved conversations and usage before loading them. It skips unusable conversation records, falls back to a valid usage state, and displays a warning if local storage cannot save the transcript. A run left active when the page closed appears as cancelled on return.

Completed API history now lives in SQLite alongside usage and request records. It survives a restart when the deployment retains that file and the browser retains its ownership cookie. Valid transcripts from the older version stay visible locally. The UI explains that the next message starts fresh assistant context, so the user knows to repeat a detail from the old exchange. [Browser recovery](../frontend/src/hooks/useChat.ts) · [Storage helpers](../frontend/src/lib/utils.ts) · [Persistence configuration](../README.md)

## 9. Diagnostics and the command-line assistant

Previously, the CLI printed raw exception details after a friendly error message. Startup and end-of-input could also bypass its handler. Meanwhile, the browser’s execution dashboard received broad tool inputs and outputs, and API errors were difficult to match to an individual request.

The CLI now handles startup failures, invalid messages, model limits, and unexpected failures with short messages. Ctrl+C and end-of-input exit the loop. Its in-memory history advances after a valid answer. In the API, HTTP responses carry an `X-Request-ID` that can help match a reported failure to server logs. This diagnostic ID identifies one HTTP attempt. The `request_id` in the chat body identifies one logical turn across retries.

The execution dashboard filters tool payloads to recognized fields, such as vehicle ID, brand, price, and loan duration. A trace can still contain the user’s question and allowed business values. The filter applies to tool payloads. [CLI](../main.py) · [Request logging](../app/api/main.py) · [Tool trace filtering](../app/api/routes/chat.py)

## Verification

The implementation verification run recorded **97 passing backend tests** and **11 passing frontend tests**. Frontend lint and the production build also passed. The run skipped 30 opt-in live-model cases and excluded the PostgreSQL integration module, which requires a dedicated writable test database. Those results cover local failure handling and simulated dependencies. They do not establish live provider or deployment health.

The regression tests include a missing SQLite path, invalid chat input, an ownership check from a second client, replay across both chat endpoints, overlapping turns, a stalled stream followed by a retry, an inventory outage, and a malformed completion event. [API tests](../app/tests/test_api.py) · [Session and retry tests](../app/tests/test_chat_usage.py) · [Streaming tests](../app/tests/test_chat_stream.py) · [Inventory tests](../app/tests/test_vehicle_ranking.py) · [Browser client tests](../frontend/tests/client.test.mjs)
