# TikTok fixtures

Authored fixtures for the `tiktok` provider contract tests. The provider reads one public
endpoint and nothing else:

```
POST https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts
website-path: tiktok
{"recruitment_id_list": [], "job_category_id_list": [], "subject_id_list": [],
 "location_code_list": [], "keyword": "", "limit": k, "offset": n}
```

Unauthenticated: no cookie, no token. `website-path` is the one required header; it names the
tenant site.

## Provenance & sanitization (D9 / §6.6 / §0 guardrail 2)

These files use the **exact response shape** of that endpoint, recorded during an attended,
read-only session on **2026-11-25** (about a dozen requests, at least one second apart,
`boardwatch-probe` User-Agent). Only the *shape* was carried over.

**All posting text is synthetic.** No real posting copy, requisition id, posting id or recruiter
contact appears here. The employer is the invented "Acme Corp"; posting ids are
`9000000000000000001`–`9000000000000000003`, requisition codes `A90001`–`A90003`. The location
names are ordinary place names, not recorded rows.

**One thing is deliberately real:** the API host `api.lifeattiktok.com` and the tenant tokens
`tiktok` and `en`, because the provider's identity *is* that host and those tokens. The ByteDance
board's tests reuse `normal.json`: its rows have the same shape (2026-11-26, two requests).

The contract tests never reach the network; they only read these files.

## Recorded envelope

```
{"code": 0, "message": "ok", "error": null,
 "data": {"job_post_list": [ {...} ], "count": N,
          "BaseResp": {"StatusMessage": "Success", "StatusCode": 0, "Extra": null}}}
```

`count` is the board's stated size (4,141 worldwide when recorded) and `board_reported_total` is
read from it.

## Recorded per-job fields

`id`, `code`, `title`, `description`, `requirement`, `recruit_type`, `job_category`, `city_info`,
`tag_list`, `job_subject`, `vacancies`, `department_info`, `job_post_info`, `process_type`,
`channel_online_status`. All 15 are reproduced. `city_info` is a city → state → country chain of
`{code, location_type, name, en_name, i18n_name, parent}` objects; a city with no state links
straight to its country. Every key under `job_post_info` (salary, degree, experience, level,
expiry) was null on every row read, so there is no posting date and no salary to parse.

## Measured limits (2026-11-25)

| request | answer |
|---|---|
| no `website-path` header (with or without `Origin`/`Referer`) | HTTP 400, body `invalid request` (`refused.txt`) |
| `website-path: tiktok`, `limit` 1 / 200 / 1000 | 1 / 200 / 1000 rows, `count` 4141 |
| `limit` 5000 | the whole board in one answer: 4,142 distinct rows, 18 MB, about 3 s |
| `offset` 4139, `limit` 5 | 2 rows: a short page ends the walk |
| a keyword that matches nothing | `code` 0, `count` 0, empty list (`empty.json`) |
| `website-path: bytedance`, on this host and on `api.joinbytedance.com` | not JSON: not a tenant here |
| `website-path: en` (2026-11-26, joinbytedance.com's own site config) | ByteDance's board: `count` 1405, the same envelope and the same 15 per-job fields, `job_post_info` all null; 25 of the store's 26 joinbytedance.com ids in it, none in `tiktok` |

## Files

- `normal.json`: three jobs. One in the US with a state, one in a country with no state
  (Singapore), one out of field (an account manager), so the location chain, the gate and the
  department are all exercised.
- `empty.json`: the measured empty answer.
- `refused.txt`: the measured body of the 400 refusal.
