# Meta Collection validate-only diagnostic

This probe compares the two Meta creation paths without creating a persistent
creative or ad:

- Test A: `POST /act_<ACCOUNT_ID>/adcreatives`
- Test B: `POST /act_<ACCOUNT_ID>/ads` with the creative inline and the existing
  Peter Brock ad set

Both requests are guarded by `execution_options=["validate_only"]`. Test B also
forces `status=PAUSED`. The probe refuses any other edge or execution option.
It is not imported by Streamlit and does not change normal Posting behaviour.

Run a local dry-run first. The values are required but are redacted from output:

```powershell
.\.venv\Scripts\python.exe scripts\validate_meta_collection_contract.py `
  --image-hash "<EXISTING_ROUTE_1_IMAGE_HASH>" `
  --product-set-id "<SELECTED_PETER_BROCK_PRODUCT_SET_ID>" `
  --primary-text "<PETER_BROCK_ROUTE_1_PRIMARY_TEXT>" `
  --headline "<PETER_BROCK_ROUTE_1_HEADLINE>"
```

The real A/B matrix must be run only inside the secured existing service
environment, where the current Meta configuration is already available. Add
`--execute` there. Do not paste tokens into command-line arguments or output.

Interpretation:

- A fails with subcode `1990065`, B validates: the standalone AdCreative path
  is the incompatibility. Production can then be changed to inline `/ads`.
- A and B fail: do not change production. Test a small evidence-based set of
  current creation-time Collection contracts inline with `validate_only`.
- A and B validate: investigate which production-only input differs before any
  retry.

The existing campaign `120249720387120554`, ad set `120249720389890554`, and
IA1 `1390026833255926` remain untouched throughout this diagnostic.
