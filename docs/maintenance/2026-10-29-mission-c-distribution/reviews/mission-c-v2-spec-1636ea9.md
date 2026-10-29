# Independent Spec review — frozen

HEAD 1636ea9fb1117dfe0c246a80f12480eaede0c39c; tree e706590f020cfe0a857411e6bcfa3610d6d004fd; base aebe8d9b440466b6b786f93461ff75715fbd935e. Reviewed all 36 changed files against supplied #43–46 snapshots, dirty-links clarification and CONTEXT. Source tree remained clean and unchanged. Read actual installed code-review skill and project entry/workflow docs.

## Blocking

**[P1] Quality admission still promotes explicit news/maintenance materials into teacher sheets.** Requirement: “新闻有人名也不因此采纳为个人页”; “维护/升级/验证页面即使200也标暂不可用，不当教师简介”; “疑似非个人、暂不可用、身份未确认不混入有/无邮箱教师表”. At `Mission C/mission_c/batch_quality.py:19`, maintenance detection checks only a narrow heading prefix. At lines24–26, even an `article.news` with a timestamp is excluded only if its heading contains seven selected event terms. Lines37–45 then promote a labelled-name or title/primary-heading candidate to workbook eligibility.

Public CLI → cached batch → export reproduced both: (1) timestamped `article.news` headed “李明教授荣获教学竞赛一等奖”, containing “姓名：李明” and explicit news/editor text, exports 李明; (2) title/h1 “维护公告” with “网站正在维护升级，暂停访问，请稍后重试。” exports a fictitious teacher named 维护公告. Both report personal_candidate/eligible=true and enter 无邮箱教师. Preserve the old extractor candidates and originals, but make new batch admission retain these explicit non-profile cases for review/unavailability.

## Nonblocking

No additional confirmed findings or scope creep. Cross-file equal IDs with different colleges were probed; IDs are workbook-local in the accepted input implementation, so that alone does not establish a conflict or blocker.

## Covered

Code inspection covers original-format import/provenance, school+stable-URL deduplication, retained college relations, shared persisted queue/locks/recovery, explicit start/pause, server policy, relative university packages/long text, standalone entrypoints and CI configuration. Existing handoff/merger evidence was read as evidence of their runs, not independent re-execution.

## Evidence / limits

Absolute TEMP prefix: C:\Users\27451\AppData\Local\Temp\.
- `mission-c-v2-spec-probe.py`; `mission-c-v2-spec-probe\summary.json`, `data-news2\` (news batch, cached original, XLSX and ZIP).
- `mission-c-v2-spec-maintenance.py`; `mission-c-v2-spec-probe\maintenance-summary.json`, `data-maintenance\` (maintenance equivalent).
- `mission-c-v2-spec-probe\cross-file-preview.json` (nonfinding).

Only synthetic local files/public CLI; no private SQL, real sites, paid API/key access, browser/full-suite rerun or source edits. An additional positive audit produced no completed summary and is not counted as validation. Exact-version CI, optional regression and physical delivery remain root gates. Overall: 1 blocking Spec finding; review does not pass.
