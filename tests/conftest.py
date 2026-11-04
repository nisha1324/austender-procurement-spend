import copy

import pytest


def make_release(cn="CN1", n=0, value="100000.00", published="2024-07-01T00:00:00Z",
                 release_date=None, method="open", supplier="Acme Pty Ltd", abn="11111111111",
                 **tender):
    """A minimal AusTender-shaped OCDS release (notice when n == 0, amendment n otherwise)."""
    rid = f"prod-{cn}-r{n}"
    contract = {
        "id": cn,
        "awardID": f"{cn}-award",
        "dateSigned": published,
        "description": "Widgets",
        "title": "REF-1",
        "items": [{"id": "x", "classification": {"scheme": "UNSPSC", "id": "43211500"}}],
        "period": {"startDate": "2024-06-30T14:00:00Z", "endDate": "2025-06-29T14:00:00Z"},
        "value": {"currency": "AUD", "amount": value},
        "status": "active",
    }
    if n:
        # Like the real API: every amendment points at the original notice's release.
        contract["amendments"] = [
            {"id": f"{cn}-A{k}", "releaseID": f"prod-{cn}-r{k}", "amendsReleaseID": f"prod-{cn}-r0"}
            for k in range(1, n + 1)
        ]
    return {
        "ocid": f"prod-{cn}",
        "id": rid,
        "date": release_date or published,
        "tag": ["contractAmendment" if n else "contract"],
        "parties": [
            {
                "id": "s1", "name": supplier, "roles": ["supplier"],
                "additionalIdentifiers": [{"id": abn, "scheme": "AU-ABN"}] if abn else [],
                "address": {"locality": "Canberra", "region": "ACT", "postalCode": "2600",
                            "countryName": "AUSTRALIA", "streetAddress": "1 Secret St"},
                "contactPoint": {"name": "An Officer", "email": "officer@agency.gov.au",
                                 "telephone": "02 0000 0000", "branch": "Procurement Branch",
                                 "division": "Corporate Division"},
            },
            {
                "id": "a1", "name": "Department of Examples", "roles": ["procuringEntity"],
                "additionalIdentifiers": [{"id": "99999999999", "scheme": "AU-ABN"}],
                "address": {}, "contactPoint": {"email": "tenders@finance.gov.au"},
            },
        ],
        "awards": [{"id": f"{cn}-award", "suppliers": [{"id": "s1", "name": supplier}],
                    "date": published}],
        "contracts": [contract],
        "tender": {"id": f"prod-{cn}", "procurementMethod": method,
                   "procurementMethodDetails": {"open": "Open tender", "limited": "Limited tender"}[method],
                   **tender},
    }


@pytest.fixture
def release():
    return lambda **kw: copy.deepcopy(make_release(**kw))
