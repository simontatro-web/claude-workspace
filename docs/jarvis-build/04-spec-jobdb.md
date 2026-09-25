# S3 spec: job database + API with the spec-approval gate

Goal: the core rule of Simon's plan: no build or research job can run unless Simon approved its spec, and a spec edited after approval is automatically unapproved. Enforced in the database and the API, not by asking a model.

Files: ~/jarvis-build/jobdb/schema.sql, db.py, api.py (FastAPI + uvicorn in the venv), test_gate.py (pytest).

Tables (SQLite, WAL, foreign_keys ON):
- specs(id, title, job_type, status CHECK in (draft, proposed, approved, superseded), body_md, approved_sha256, approved_at, created_at, updated_at)
- spec_turns(id, spec_id, role CHECK in (jarvis, simon), text, created_at): every interview question and answer, saved as it happens
- jobs(id, spec_id NULL, type, status CHECK in (queued, running, done, failed, paused), payload_json, result_json, max_seconds, created_at, claimed_at, finished_at)
- events(id, time, source, kind, job_id NULL, message): append-only log
- approvals(id, kind, ref_id, status CHECK in (pending, approved, denied), token_sha256, created_at, decided_at, reason)

Gate rules (all three must exist):
1. Trigger: INSERT into jobs with type in (build, research, self_change) and spec_id NULL -> RAISE(ABORT).
2. Claim (POST /jobs/claim): claims the oldest queued job ONLY if it has no spec (type echo) OR its spec status = approved AND approved_sha256 = sha256(body_md). Claim is one atomic UPDATE ... RETURNING under a lock (no double claims).
3. Approval: POST /specs/{id}/approve requires header X-Approve-Token matching the one-time token of a pending approvals row for that spec (store only its sha256). On success: status approved, approved_sha256 = sha256(body_md), token row marked used. A reused or wrong token -> 403.
Also: PUT /specs/{id} (edit body) sets status back to draft if it was approved.

Other endpoints: POST /specs, POST /specs/{id}/turns, POST /specs/{id}/propose (creates the pending approval, returns the token ONCE; later Claude will route it to Simon's phone), POST /jobs, GET /jobs/{id}, GET /status (counts per status + last 20 events), GET /health. Every state change writes an event.

Run: uvicorn on 127.0.0.1:8111 only. DB file: ~/jarvis-build/jobdb/test.db for tests.

Tests (pytest, paste the summary line):
- build job without spec -> rejected
- job with draft spec -> never claimed
- approve with wrong token -> 403; with right token -> approved; same token again -> 403
- edit approved spec -> back to draft -> its job no longer claimable
- approved spec job -> claimed exactly once
- 8 concurrent claim calls on 5 echo jobs -> 5 distinct claims, 3 "nothing to claim", 0 errors
- /status returns counts that match the rows

Known limit (write it in PROGRESS.md): until Simon creates the separate users, Jarvis's shell could edit test.db directly. The gate becomes unbreakable only after that step. Do not work around the gate yourself.
