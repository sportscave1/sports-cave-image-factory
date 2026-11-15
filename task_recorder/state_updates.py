"""Bounded catalogue deltas; data only, never browser actions or credentials."""
from .schema import Invalid

SUMMARY_FIELDS={"attention","issue_count","id","name","last_run","result","revision","inputs","steps","duration_ms","updated_at","format","format_version","capabilities","playback_available"}

def task_changes(previous,current):
    old={row["id"]:row for row in previous}
    new={row["id"]:row for row in current}
    return {"upsert":[row for key,row in new.items() if old.get(key)!=row],
            "remove":[key for key in old if key not in new]}

def merge_tasks(previous,patch):
    from uuid import UUID
    if not isinstance(patch,dict) or set(patch)!={"upsert","remove"} or not all(isinstance(patch[k],list) for k in patch):
        raise Invalid("Invalid task summary update.")
    try:
        removed=[str(UUID(key)) for key in patch["remove"]]
        upsert=patch["upsert"]
        ids=[str(UUID(row["id"])) for row in upsert if isinstance(row,dict) and not set(row)-SUMMARY_FIELDS]
        if len(ids)!=len(upsert) or len(ids)!=len(set(ids)) or len(removed)!=len(set(removed)) or set(ids)&set(removed):raise ValueError()
    except (ValueError,KeyError,TypeError,AttributeError):raise Invalid("Invalid task summary update.")
    rows={row["id"]:row for row in previous if row["id"] not in removed}
    rows.update(zip(ids,upsert))
    return sorted(rows.values(),key=lambda row:(str(row.get("name","")).lower(),row["id"]))
