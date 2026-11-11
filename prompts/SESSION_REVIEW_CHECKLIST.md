# Human Review Checklist (Before Importing Gemini JSON)

Inspect every draft in `.mastery/inbox/` against this checklist before changing `"review_status"` to `"accepted"` and running `import-record`:

- [ ] **Session identity:** `session_id`, `date`, `topic_ids` (`T-001`–`T-025`), and `task_ids` match what actually occurred.
- [ ] **No fabricated history:** No invented `E-000`–`E-041`, `M-001`–`M-019`, `R-001`–`R-008`, commit hashes, or file paths.
- [ ] **Hint & attempt honesty:** `attempt_type` (`first_attempt` vs `remediation` vs `transfer` vs `delayed_recall`) and `hint_level` (`H0`–`H4`) accurately reflect any tutor assistance. Remediations/corrections link `parent_session_id`.
- [ ] **Objective evidence verified:** `code_files` exist in the repository; `test_command`, `test_returncode`, and `test_output_excerpt` match actual `.mastery/evidence/*-test.json` output (not assumed passing).
- [ ] **Dimensions grounded:** Each `0–5` dimension score is backed by observed transcript/code evidence; unobserved dimensions are `null`.
- [ ] **Mistakes accurately separated:** `observable_symptom`, `original_incorrect_reasoning`, `root_cause`, and `correction` are distinct; recurrences link `recurrence_of`. Status is not prematurely marked `resolved_verified_delayed`.
- [ ] **Retention honesty:** `probe_id_attempted` and `probe_outcome` accurately match the probe actually taken; no future probes are pre-marked completed or verified.
- [ ] **Human approval set:** Explicitly update `"review_status": "accepted"`, `"reviewed_by_human": true`, and `"reviewed_at": "<ISO-8601>"` only after completing this review.
