"""Unwired financial-only transaction handlers for a separately approved canary.

No connection creation, provider calls, implicit DDL, UI, worker or apply CLI.
The trusted operator supplies an idle connection, fresh captures and an exact
approval record. The record documents approval; it is not an authentication API.
"""
from datetime import datetime, timezone
from decimal import Decimal
import json
import re
import psycopg
from psycopg.pq import TransactionStatus
from shopify_financial_repair import LEDGER_QUERY, digest, preview, timestamp, validate_ids

SOURCE = "shopify_financial_canary_v1"
REVIEWED_GUARD_MD5 = "023848686d5ca5aa31ede7286046835b"
FIELDS = ("total_price", "currency", "raw_json_amount", "raw_json_currency", "raw_amount", "raw_currency",
          "raw_json_has_amount", "raw_json_has_currency", "raw_has_amount", "raw_has_currency", "raw_json_is_null", "raw_is_null")
READ_SQL = """SELECT d.*,o.cancelled_at,
    coalesce(o.raw_json ? 'total_price',false) raw_json_has_amount,coalesce(o.raw_json ? 'currency',false) raw_json_has_currency,
    coalesce(o.raw ? 'total_price',false) raw_has_amount,coalesce(o.raw ? 'currency',false) raw_has_currency,
    o.raw_json IS NULL raw_json_is_null,o.raw IS NULL raw_is_null,
    jsonb_typeof(o.raw_json) raw_json_type,jsonb_typeof(o.raw) raw_type
    FROM (""" + LEDGER_QUERY + ") d JOIN shopify_orders o USING(shopify_order_id) ORDER BY d.shopify_order_id"
CONTRACT_SQL = """SELECT jsonb_build_object(
 'triggers',(SELECT coalesce(jsonb_agg(jsonb_build_object('table',c.relname,'name',t.tgname,'enabled',t.tgenabled,
   'definition',pg_get_triggerdef(t.oid),'function_md5',md5(pg_get_functiondef(t.tgfoid))) ORDER BY c.relname,t.tgname),'[]'::jsonb)
   FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid WHERE t.tgrelid IN ('shopify_orders'::regclass,'audit_logs'::regclass) AND NOT t.tgisinternal),
 'rules',(SELECT coalesce(jsonb_agg(r.rulename ORDER BY r.rulename),'[]'::jsonb) FROM pg_rewrite r
   WHERE r.ev_class IN ('shopify_orders'::regclass,'audit_logs'::regclass) AND r.rulename<>'_RETURN')) AS contract"""


class Conflict(ValueError):
    pass


class OutcomeUnknown(RuntimeError):
    pass


def clean(value):
    return json.loads(json.dumps(value, default=lambda v: v.isoformat() if isinstance(v,datetime) else str(v)))


def read_rows(conn, ids, *, lock=False):
    return clean(conn.execute(READ_SQL + (" FOR UPDATE OF o" if lock else ""), (validate_ids(ids),)).fetchall())


def read_contract(conn):
    return conn.execute(CONTRACT_SQL).fetchone()["contract"]


def state(row):
    result = {key:row[key] for key in (*FIELDS, "shopify_order_id", "protected_hash", "updated_at", "remote_updated_at", "synced_at")}
    for key in ("updated_at", "remote_updated_at", "synced_at"):
        if result[key] is not None: result[key] = timestamp(result[key]).astimezone(timezone.utc).isoformat()
    return result


def prepare(ids, ledger, provider, contract):
    ids = validate_ids(ids)
    if len(ids)>6:
        raise ValueError("This canary is limited to six explicitly selected orders.")
    baseline = preview(ids,ledger,provider)
    if any(c["status"] != "proposed" for c in baseline["changes"]):
        raise Conflict("Only missing, non-conflicting financial pairs may be repaired.")
    if contract.get("rules") or any(t["table"]!="shopify_orders" or t["name"]!="cancelled_edition_order_guard"
        or t.get("enabled")!="O" or t.get("function_md5")!=REVIEWED_GUARD_MD5 for t in contract.get("triggers",[])):
        raise Conflict("Unreviewed database trigger or rule; canary is blocked.")
    rows = {r["shopify_order_id"]:r for r in clean(ledger["rows"])}
    for row in rows.values():
        if row.get("cancelled_at") or row.get("raw_json_type") not in (None,"object") or row.get("raw_type") not in (None,"object"):
            raise Conflict("Cancelled order or unsupported raw JSON shape.")
        for name in FIELDS:
            if name not in row: raise ValueError("Capture exact financial key presence before preparing the canary.")
    changes=[]
    for c in baseline["changes"]:
        row=rows[c["shopify_order_id"]]
        after=c["proposed_after"]
        # Valid raw financial evidence must not be silently overwritten either.
        for prefix in ("raw_json", "raw"):
            amount,currency=row[prefix+"_amount"],row[prefix+"_currency"]
            if amount is not None and str(amount).strip() and Decimal(str(amount))!=Decimal(after["total_price"]):
                raise Conflict("Existing raw amount conflicts with the provider.")
            if currency is not None and str(currency).strip() and currency!=after["currency"]:
                raise Conflict("Existing raw currency conflicts with the provider.")
        times = {k:timestamp(v).astimezone(timezone.utc).isoformat() if v is not None else None
                 for k,v in c["source_times"].items()}
        changes.append({"id":c["shopify_order_id"],"before":state(row),"after":after,"source_times":times})
    result={"schema":2,"operation":"financial_canary","mode":"dry_run_only","production_authorized":False,
            "changes":changes,"database_contract":contract,"ledger_captured_at":timestamp(ledger["captured_at"]).astimezone(timezone.utc).isoformat(),
            "provider_captured_at":timestamp(provider["captured_at"]).astimezone(timezone.utc).isoformat(),"credential_context":provider.get("credential_context"),
            "shop_domain":provider.get("shop_domain"),"served_api_version":provider.get("served_api_version")}
    return {**result,"operation_hash":digest(result)}


def validate(manifest):
    body={k:v for k,v in manifest.items() if k!="operation_hash"}
    if body.get("schema")!=2 or body.get("operation")!="financial_canary" or digest(body)!=manifest.get("operation_hash"):
        raise Conflict("Manifest content/hash mismatch.")
    ids=validate_ids([c["id"] for c in manifest["changes"]])
    if len(ids)>6: raise Conflict("Canary row limit exceeded.")
    return ids


def grant(manifest, approval, action, runtime_revision, at):
    if (set(approval)!={"release_sha","operation_hash","action","order_ids","actor","approval_ref","approved_at","expires_at"}
        or not re.fullmatch(r"[0-9a-f]{40}",str(runtime_revision)) or approval.get("release_sha")!=runtime_revision
        or approval.get("operation_hash")!=manifest["operation_hash"] or approval.get("action")!=action
        or approval.get("order_ids")!=validate(manifest) or not re.fullmatch(r"[A-Za-z0-9_.:@-]{1,120}",str(approval.get("actor","")))
        or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}",str(approval.get("approval_ref","")))):
        raise PermissionError("Exact action, IDs, actor, approval reference and runtime revision are required.")
    if not timestamp(approval["approved_at"])<=at<timestamp(approval["expires_at"]):
        raise PermissionError("Approval is not currently valid.")


def fresh(manifest, provider, at):
    for captured in (manifest["ledger_captured_at"], manifest["provider_captured_at"],provider["captured_at"]):
        if not 0 <= (at-timestamp(captured)).total_seconds() <= 300:
            raise Conflict("A capture is stale/future-dated; refresh the read-only manifest.")
    if (provider.get("credential_context")!="OS Shopify server integration"
        or manifest.get("credential_context")!=provider["credential_context"]
        or not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.myshopify\.com",str(provider.get("shop_domain","")))
        or manifest.get("shop_domain")!=provider["shop_domain"] or not provider.get("served_api_version")
        or manifest.get("served_api_version")!=provider["served_api_version"]):
        raise Conflict("Provider credential, shop and served API version must match the approved capture.")
    rows={r["id"]:r for r in provider["rows"] if r}
    if len(rows)!=len(provider["rows"]) or sorted(rows)!=validate(manifest): raise Conflict("Incomplete provider capture.")
    for c in manifest["changes"]:
        row=rows[c["id"]];money=row["totalPriceSet"]["shopMoney"]
        if (timestamp(row["updatedAt"])!=timestamp(c["source_times"]["provider_updated_at"])
            or timestamp(row["processedAt"])!=timestamp(c["source_times"]["provider_processed_at"])
            or Decimal(money["amount"])!=Decimal(c["after"]["total_price"]) or money["currencyCode"]!=c["after"]["currency"]):
            raise Conflict("Provider state changed; a new manifest/approval is required.")


def audit(conn, key):
    rows=conn.execute("SELECT event_type,old_value,new_value FROM audit_logs WHERE source=%s AND entity_type='financial_canary' AND entity_id=%s ORDER BY id",(SOURCE,key)).fetchall()
    sequence=[row["event_type"] for row in rows]
    if sequence not in ([],["financial_canary_applied"],["financial_canary_applied","financial_canary_rolled_back"]):
        raise Conflict("Unexpected audit history needs manual reconciliation.")
    return rows


def reconcile(conn, manifest):
    """Read-only; call on a fresh connection after any uncertain commit."""
    ids=validate(manifest)
    if conn.info.transaction_status!=TransactionStatus.IDLE: raise ValueError("Supply an idle dedicated connection.")
    with conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL statement_timeout='8000ms'")
        logs=audit(conn,manifest["operation_hash"])
        if not logs: return {"status":"not_applied","operation_hash":manifest["operation_hash"]}
        current=[state(r) for r in read_rows(conn,ids)]
        return {"status":logs[-1]["event_type"],"state_verified":current==logs[-1]["new_value"]["states"],
                "operation_hash":manifest["operation_hash"]}


def write_financial(conn, identifier, values):
    raw={}
    for prefix in ("raw_json","raw"):
        raw[prefix]={key:values[prefix+"_"+suffix] for key,suffix in (("total_price","amount"),("currency","currency"))
                     if values[prefix+"_has_"+suffix]}
    changed=conn.execute("""UPDATE shopify_orders SET total_price=%s,currency=%s,
      raw_json=CASE WHEN %s THEN NULL ELSE (coalesce(raw_json,'{}'::jsonb)-'total_price'-'currency')||%s::jsonb END,
      raw=CASE WHEN %s THEN NULL ELSE (coalesce(raw,'{}'::jsonb)-'total_price'-'currency')||%s::jsonb END,
      updated_at=clock_timestamp() WHERE shopify_order_id=%s RETURNING shopify_order_id""",
      (values["total_price"],values["currency"],values["raw_json_is_null"],json.dumps(raw["raw_json"]),
       values["raw_is_null"],json.dumps(raw["raw"]),identifier)).fetchall()
    if len(changed)!=1: raise Conflict("Order disappeared while applying canary.")


def _run(conn, manifest, approval, runtime_revision, *, provider=None, rollback=False, at=None):
    ids=validate(manifest);at=at or datetime.now(timezone.utc);action="rollback" if rollback else "apply"
    grant(manifest,approval,action,runtime_revision,at)
    if conn.info.transaction_status!=TransactionStatus.IDLE: raise ValueError("Supply an idle dedicated connection.")
    try:
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='8000ms'")
            conn.execute("SET LOCAL lock_timeout='3000ms'")
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(SOURCE+manifest["operation_hash"],))
            # Prevent trigger/schema changes during verification; ordinary writers still use row locks.
            conn.execute("LOCK TABLE shopify_orders,audit_logs IN ROW EXCLUSIVE MODE")
            logs=audit(conn,manifest["operation_hash"])
            rows=read_rows(conn,ids,lock=True)
            before=[state(r) for r in rows]
            if len(rows)!=len(ids): raise Conflict("Missing canary order.")
            if read_contract(conn)!=manifest["database_contract"]: raise Conflict("Database trigger/rule contract changed.")
            if logs and logs[-1]["event_type"]==("financial_canary_rolled_back" if rollback else "financial_canary_applied"):
                if before!=logs[-1]["new_value"]["states"]: raise Conflict("Already completed, but final state has changed. Reconcile without replay.")
                return {"status":"already_rolled_back" if rollback else "already_applied","writes":0,"operation_hash":manifest["operation_hash"]}
            if rollback:
                if len(logs)!=1 or logs[0]["event_type"]!="financial_canary_applied": raise Conflict("No applied canary to roll back.")
                if before!=logs[0]["new_value"]["states"]: raise Conflict("After-image changed; rollback refused.")
                targets=logs[0]["old_value"]["states"]
            else:
                if logs: raise Conflict("Rolled-back canary cannot be applied again; prepare a new manifest.")
                fresh(manifest,provider,at)
                if before!=[c["before"] for c in manifest["changes"]]: raise Conflict("Before-image changed; no rows updated.")
                targets=[]
                for c in manifest["changes"]:
                    amount,currency=c["after"]["total_price"],c["after"]["currency"]
                    target={**c["before"],"total_price":amount,"currency":currency}
                    for prefix in ("raw_json","raw"):
                        target.update({prefix+"_amount":amount,prefix+"_currency":currency,prefix+"_has_amount":True,
                                       prefix+"_has_currency":True,prefix+"_is_null":False})
                    targets.append(target)
            for target in targets: write_financial(conn,target["shopify_order_id"],target)
            after=[state(r) for r in read_rows(conn,ids)]
            for actual,target,original in zip(after,targets,before):
                if any(actual[k]!=target[k] for k in FIELDS) or actual["protected_hash"]!=original["protected_hash"]:
                    raise Conflict("Post-write verification failed; transaction rolled back.")
            event="financial_canary_rolled_back" if rollback else "financial_canary_applied"
            receipt={"states":after,"approval":approval,"release_sha":runtime_revision,"operation_hash":manifest["operation_hash"]}
            conn.execute("""INSERT INTO audit_logs(event_type,entity_type,entity_id,old_value,new_value,reason,actor,source)
                VALUES(%s,'financial_canary',%s,%s::jsonb,%s::jsonb,%s,%s,%s)""",
                (event,manifest["operation_hash"],json.dumps({"states":before}),json.dumps(receipt),
                 "Approved financial-only canary "+action,approval["actor"],SOURCE))
        return {"status":event,"writes":len(ids),"operation_hash":manifest["operation_hash"]}
    except (psycopg.OperationalError,psycopg.InterfaceError):
        raise OutcomeUnknown("Commit outcome requires read-only audit/state reconciliation; do not blindly retry.") from None


def apply(conn,manifest,approval,provider,*,runtime_revision,at=None):
    return _run(conn,manifest,approval,runtime_revision,provider=provider,at=at)


def rollback(conn,manifest,approval,*,runtime_revision,at=None):
    return _run(conn,manifest,approval,runtime_revision,rollback=True,at=at)
