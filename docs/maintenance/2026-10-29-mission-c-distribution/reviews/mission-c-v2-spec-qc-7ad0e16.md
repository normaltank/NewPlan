# Incremental Spec review — frozen

Base1636ea9fb1117dfe0c246a80f12480eaede0c39c → fixed HEAD7ad0e16a3ef55656613fc08962d5cd74cbbbbb31/tree f6ba8c91dc4fac5e6a2f026ecd1f4e12ef8c65ec. Reviewed complete three-file delta: BATCH.md, batch_quality.py, test_batch.py. Source clean before/after; no edits. Same #43–46/dirty-page/CONTEXT requirements as initial review. New distribution UI excluded from scope.

## Blocking

**[P1] Explicit maintenance/interruption pages still enter teacher delivery under common alternate headings.** Requirement: “维护/升级/验证页面即使200也标暂不可用，不当教师简介”; “疑似非个人、暂不可用、身份未确认不混入有/无邮箱教师表”. `Mission C/mission_c/batch_quality.py:19–23` recognizes only selected heading prefixes; interruption text is effective only when `notice` matches a maintenance/upgrade announcement title. The title/primary-heading candidate admission at lines49–54 then mistakes the remaining service-page headings for reliable identity.

Independent public CLI/cache→export reproduces: title/h1 “正在维护” plus “网站正在维护升级，暂停访问，请稍后重试。” becomes a teacher named 正在维护; title/h1 “访问提示” plus “系统正在升级维护，暂时无法访问，请稍后重试。” becomes teacher 访问提示. Both HTTP200 entries report personal_candidate/eligible=true and appear in 无邮箱教师. This is the original maintenance root cause under equivalent interruption templates, not a request for universal webpage classification. Keep original candidates/raw evidence while denying teacher admission for these explicit service-state materials.

## Nonblocking

No additional confirmed findings or scope creep in this delta.

## Covered independently

One seven-task synthetic batch: original award-news → suspected_non_personal; original maintenance-notice → temporarily_unavailable; alternative talent-award news → suspected_non_personal; normal profile and article.news/time profile with maintenance research/award history → personal_candidate. All seven raw HTML originals match ZIP bytes. records.json7, exceptions3, workbook three fixed sheets, but teacher rows4 include the two false maintenance identities. Original P1 therefore only partially resolved.

## Evidence and limits

Absolute TEMP prefix C:\Users\27451\AppData\Local\Temp\:
- mission-c-v2-spec-qc-7ad0e16-probe.py
- mission-c-v2-spec-qc-7ad0e16-evidence\: summary.json, commands.json (import/run/export all exit0), status.json, seven HTML inputs, original-format review.xlsx, cache manifest and persistent data/ZIP.

Producer nine-task/cache audits and merger five/post-two tests were read with their stated version limits; they are not my independent runs. No private SQL, source edits, real sites, key/paid calls, full-suite or browser reruns. No CI/deployment claim. Overall: 1 blocking Spec finding; incremental review does not pass.
