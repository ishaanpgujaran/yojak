## 1. `test_main.py`

### A. Active authorization with missing scopes
Suppose the merchant originally granted:
- `ZohoInventory.items.READ`
- `ZohoInventory.salesorders.READ`

But Yojak now requires `ZohoInventory.settings.READ` as well. The connect endpoint should detect the missing scope and initiate OAuth consent again.

### B. Active authorization with an invalid refresh token
The connect endpoint attempts to reuse the existing authorization. If Zoho responds with `invalid_code`, the authorization should be marked revoked and a new OAuth flow should begin.

### C. Active authorization with a different refresh failure
For example, `invalid_client_secret`. This should not be treated as a revoked merchant authorization. The endpoint should return an error rather than silently initiate a new consent flow.

> These cases matter because they test the decisions your OAuth lifecycle implementation makes.

---

## 2. `test_zoho_auth.py`

We should add tests for:
1. All required scopes are granted → no missing scopes.
2. One required scope is missing → only that scope is returned.
3. Multiple required scopes are missing → all missing scopes are returned.
4. Extra granted scopes are present → they don't cause a failure.
5. Whitespace and duplicate scope values are handled correctly.

> These are small unit tests, but they protect an important part of the authorization lifecycle.

---

## 3. `test_repositories.py`

I don't recommend adding more repository tests just yet. The names establish that these scenarios exist, but I'd need to inspect their assertions before declaring every detail fully covered.

---

## 4. The biggest gap: OAuth callback testing

Your complete `test_main.py` contains no callback tests. That means we haven't yet demonstrated automated coverage for the complete callback lifecycle:
- Invalid or missing OAuth state.
- Reusing an already-consumed state.
- Successful authorization-code exchange.
- Refresh-token encryption and database persistence.
- Reauthorization updating the existing authorization record.
- Failure during authorization-code exchange.
- Failure while persisting the authorization.
- Safe handling when no authorization record is returned.

> This is particularly important because the callback is where Zoho's authorization response becomes a persisted Yojak authorization.

---

## Our updated testing roadmap

I'd organize the remaining work like this:

| Priority | Test area | Action |
| :--- | :--- | :--- |
| **1** | OAuth scope helpers | Add unit tests |
| **2** | `/oauth/zoho/connect` | Add missing-scope and refresh-failure tests |
| **3** | `/oauth/zoho/callback` | Add callback lifecycle tests |
| **4** | Repository tests | Inspect existing assertions for completeness |
| **5** | Full test suite | Execute all tests and resolve failures |
| **6** | End-to-end verification | Test with an actual Zoho account |
