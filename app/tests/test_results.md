# Test results log

Add a new dated entry for each run so earlier results stay available for comparison. Record the code revision or working tree, command, model if used, database or fixture, pass/fail/skip counts, and the reasons for failures or skips.

## 2026-11-24 — Initial agent evaluation suite verification

- **Logged at** 2026-11-24 16:06:37 IST (UTC+05:30). The previous run took place on 2026-11-24. Its exact start time was not captured.
- **Code** Local working tree with the new evaluation suite.
- **Focused run** `python -m pytest -q -p no:cacheprovider app/tests/test_agent_evaluation.py` — **1 passed, 30 skipped** in 1.29 s.
- **Full backend run** `python -m pytest -q -p no:cacheprovider` — **89 passed, 6 failed, 30 skipped** in 6.20 s. This run includes the focused harness test.
- **Live model** 0 of 30 scenarios ran because `RUN_AGENT_EVALS` was unset. This entry establishes a baseline for application tests and the eval harness. Live task success, latency, and token usage have no baseline yet.

| Area | What the run exercised | Result |
| --- | --- | --- |
| Agent evaluation harness | A scripted LangChain model called the real search tool against an in-memory catalogue. The grader accepted the correct shortlist and rejected a reply with the wrong variant. | Passed |
| Chat API | Health endpoint, session creation and reuse, usage limits, per-IP rate limiting, error handling, and exposed routes. Chat tests used a test double. | Passed |
| Chat streaming | Event lifecycle, session IDs, early text delivery, tool progress, heartbeat, cancellation on disconnect, and sanitized terminal errors. A scripted LangChain model exercised the real streaming path. | Passed |
| Usage tracking | Conversation reset, shared usage limits across routes, the 24-hour window, and concurrent requests staying within the budget. | Passed |
| Finance | EMI and total repayment, zero interest, rounding, input bounds, validation, and tool result serialization. | Passed |
| Service health | Dependency status, missing database configuration, sanitized database failures, and provider health checks. | Passed |
| Catalogue ranking | Filtering, sort order, ties, shortlist limits, variant selection, and invalid search filters using a controlled SQLite catalogue. | Passed |
| PostgreSQL integration | Brand and price filtering, shortlist order, inclusive ranges, lookup by ID, missing ID, and separate variant lookup. The optional-variant model check also ran. | 6 failed, 1 passed |
| Live agent behavior | The [evaluation suite](../../docs/test-suite-doc.md) contains 30 scenarios for real model behavior. | Skipped |

All six failures were in `test_vehicle_service.py`. The configured local PostgreSQL database had a `vehicles` table without the `variant` column required by the current repository schema.

- `test_search_by_brand_and_price`
- `test_search_shortlist_and_price_order`
- `test_search_model_variants_and_inclusive_range`
- `test_get_vehicle_by_id`
- `test_get_missing_vehicle`
- `test_separate_variant_search_and_details`

Frontend checks were outside this backend pytest run.

## 2026-11-24 — First live OpenRouter core baseline

- **Run window** 16:42:28–16:44:26 IST (UTC+05:30). Pytest reported 115.44 s.
- **Configuration** Local working tree, `nvidia/nemotron-3.5-lightning:free`, synthetic SQLite catalogue, 30-request ceiling, four-second spacing. The runner used the configured `OPENROUTER_API_KEY` because `OPENROUTER_EVAL_API_KEY` was unset.
- **Command** `RUN_AGENT_EVALS=1` and `AGENT_EVAL_BATCH=core`, with `python -m pytest -q -rs --tb=line -p no:cacheprovider --basetemp=<fresh directory> app/tests/test_agent_evaluation.py -k test_live_agent --junitxml=<report> -o junit_family=xunit1`.
- **Result** 12 passed, 2 failed, 0 skipped among 14 selected scenarios (85.7%). The offline harness was deselected and the 16 extended scenarios were outside this run.
- **Quota** 28 outbound request attempts of the 30 allowed. No HTTP 429 or budget stop was recorded.
- **Latency** Over 15 completed turns, p50 was 7.67 s and p95 was 12.04 s (nearest rank). These times include request pacing and tool work. The failed repository turn had no completed reply and is excluded.
- **Token usage** 99,228 reported input and output tokens combined across all 15 completed turns. Usage for the first model response in the failed repository turn was unavailable in the report, so this is a partial total for the run.
- **Cost** Used the free model. The runner did not collect billing data.

| Scenario | Result | Request attempts |
| --- | --- | ---: |
| `strict-budget` | Pass | 2 |
| `price-range` | Pass | 2 |
| `descending-price` | Pass | 2 |
| `exact-variant` | Pass | 2 |
| `details-found` | Pass | 2 |
| `emi-complete` | Pass | 2 |
| `emi-down-payment` | Pass | 2 |
| `emi-missing-inputs` | Pass | 1 |
| `retain-budget` | Pass | 4 |
| `resolve-reference` | Pass | 3 |
| `general-question` | Fail. The agent answered without a tool and used “Sports Utility Vehicle.” The grader required “Sport Utility.” | 1 |
| `unsupported-mileage` | Pass | 2 |
| `empty-search` | Pass | 2 |
| `repository-failure` | Fail. The injected `ConnectionError` escaped the tool path before the assistant could explain the failure to the customer. | 1 |

An initial attempt at 16:42:09 IST hit a Windows permission error in pytest's default temporary directory. It stopped during setup with 14 errors and sent zero model requests. The baseline above comes from the retry with a fresh temporary directory.

### OpenRouter activity for the same run

The 28 dashboard rows supplied for this run show **93,844 input tokens**, **8,656 output tokens**, and **102,500 total tokens**, with **$0.00 displayed cost**. Input accounted for **91.6%** of usage. The dashboard total exceeds the original JUnit subtotal by **3,272 tokens**, exactly matching the last recorded tool-call request (3,153 input and 119 output). That is consistent with the missing usage from the interrupted repository-failure turn.

Across those 28 requests, OpenRouter's **time to first token** was **0.35 s at p50** and **0.98 s at p95** (nearest rank), with a range of **0.32–1.21 s**. This is a per-request provider metric. A tool-call token can arrive before any text is visible, and a single conversation turn can contain multiple requests. The original run did not measure time to first visible text.

NVIDIA reported **2,112 cached prompt tokens on each of the 28 requests**, according to the OpenRouter dashboard. All 28 requests had a prompt cache hit. Across the run, **59,136 of 93,844 input tokens (63.0%)** were served from cache, leaving **34,708 input tokens** outside the cache. The cached tokens are included in the input total. This run provides a latency baseline with a cache hit on every request.
