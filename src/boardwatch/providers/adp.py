"""ADP WorkforceNow: the URL mapping the liveness probe needs, and nothing else (D-684).

Not a board provider: nothing here scans, and ADP is not in `registry.PROVIDER_CLASSES`. Every ADP
posting boardwatch holds arrives through an aggregator or the job-apps lane under an unwatched
company, so no scan has ever been able to close one, and the recruitment page cannot say whether
one is open: it is one JavaScript shell for every jobId (12 captures from two tenants,
byte-identical).

The public requisition resource can. It takes the same `jobId` the page URL carries (ADP's
`ExternalJobID`) and answers a posted requisition with its record and an unposted one with an
exactly-empty object; `core/liveness.verdict_for_adp_requisition` reads that.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

_PAGE_HOST = "workforcenow.adp.com"
_PAGE_PATH = "/mascsr/default/mdf/recruitment/recruitment.html"
_CID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_JOB_ID = re.compile(r"^\d{1,12}$")
# The one career-center id the controls covered, on both tenants. Another `ccId` (a tenant can have
# several) is a shape nothing was measured on, so it keeps the plain page probe.
MEASURED_CC_ID = "19000101_000001"


def requisition_url_for_page(url: str) -> str | None:
    """The public requisition resource for one posting's recruitment-page URL, or None.

    `https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html?cid=<uuid>
    &ccId=19000101_000001&jobId=<digits>` and nothing looser. Tracking parameters (`source=IN`,
    `jwId`, `lang`) are ignored: they are not identity.
    """
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != _PAGE_HOST or parts.port is not None:
        return None
    if parts.username or parts.password or parts.path != _PAGE_PATH:
        return None
    query = parse_qs(parts.query, keep_blank_values=True)
    values = {key: query.get(key, []) for key in ("cid", "ccId", "jobId")}
    if any(len(found) != 1 for found in values.values()):
        return None
    cid, cc_id, job_id = (values[key][0] for key in ("cid", "ccId", "jobId"))
    if not _CID.match(cid) or cc_id != MEASURED_CC_ID or not _JOB_ID.match(job_id):
        return None
    return (
        f"https://{_PAGE_HOST}/mascsr/default/careercenter/public/events/staffing/v1/"
        f"job-requisitions/{job_id}?cid={cid}&ccId={cc_id}&lang=en_US&locale=en_US"
    )
