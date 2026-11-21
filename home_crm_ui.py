"""Small Home CRM table and nonblocking, accessible refresh controls."""
from html import escape
import json
from datetime import timedelta
import math

CHANNELS = ("Facebook paid", "Google paid", "Organic", "Other", "Unresolved")


def html(today, initial=None):
    day = str(today - timedelta(days=1))
    # Only aggregate data is passed to the client. The backend never returns order IDs.
    initial = initial or {"state": "loading", "data": None}
    data = initial.get("data") or {}
    ledger = data.get("ledger") or {}
    indexed = {row["channel"]: row for row in ledger.get("rows", [])}
    def count(name, key):
        value = indexed.get(name, {}).get(key)
        return f"{value:,}" if type(value) is int and value >= 0 else "—"
    def ratio(name):
        value = data.get("roas", {}).get(name)
        return f"{value:.2f}×" if type(value) in (float, int) and math.isfinite(value) else "—"
    rows = "".join('<tr data-channel="' + escape(name) + '"><th scope="row">' +
        escape(name) + '</th>' + ''.join('<td data-device="' + key + '">' + count(name, key) + '</td>'
            for key in ("mobile", "desktop", "other", "total")) + '</tr>' for name in CHANNELS)
    options = "".join('<option value="' + key + '">' + label + '</option>' for key, label in (
        ("yesterday", "Yesterday"), ("week", "Last 7 days"), ("month", "Last 30 days"),
        ("quarter", "Last 3 months"), ("today", "Today")))
    payload = json.dumps(initial).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return f"""<section class="sc-home-crm" aria-label="CRM source and device snapshot" data-initial="{escape(payload, quote=True)}">
      <div class="sc-crm-controls"><label>Results <select aria-label="CRM reporting period">{options}</select></label>
        <button type="button" class="sc-crm-refresh">Refresh</button><small class="sc-crm-dates">{day}</small></div>
      <div class="sc-crm-paid"><span>Facebook / Instagram ROAS <b data-roas="facebook">{ratio("facebook")}</b></span>
        <span>Google ROAS <b data-roas="google">{ratio("google")}</b></span></div>
      <div class="sc-crm-table-wrap"><table><caption>Shopify orders · GA4 source and device</caption>
        <thead><tr><th scope="col">Source</th><th scope="col">Mobile</th><th scope="col">Desktop</th>
        <th scope="col">Other /<br>unknown</th><th scope="col">Total</th></tr></thead><tbody>{rows}</tbody></table></div>
      <small class="sc-crm-status" role="status" aria-live="polite">Loading verified results…</small>
      <details class="sc-crm-coverage"><summary>Coverage &amp; attribution</summary><p class="sc-crm-basis"></p>
        <p>Other includes direct, email and other referrals. Unresolved includes missing or conflicting source evidence.
        Tablets and unknown devices stay in Other / unknown. Organic has no advertising ROAS.</p>
        <p class="sc-crm-sources"></p><p>Paid-platform ROAS can overlap and is separate from the order table.
        Facebook includes Instagram. Google covers PM021126. Values can change as conversions arrive.</p></details>
    </section>"""


CSS = """<style>
.sc-home-crm{border:1px solid #9f875c44;border-radius:12px;padding:.65rem .8rem;font-size:.77rem;line-height:1.35;background:var(--background-color,#fff)}
.sc-crm-controls{display:flex;align-items:center;gap:.55rem;flex-wrap:wrap;margin-bottom:.5rem}
.sc-crm-controls label{display:flex;align-items:center;gap:.35rem}
.sc-crm-controls select,.sc-crm-controls button{font:inherit;color:inherit;background:transparent;border:1px solid #9f875c55;border-radius:5px;padding:.2rem .4rem}
.sc-crm-dates{margin-left:auto}.sc-crm-paid{display:flex;gap:.6rem;flex-wrap:wrap;margin-bottom:.5rem}
.sc-crm-paid span{flex:1;border-top:2px solid #b49048;padding:.35rem .4rem;background:#b490480b;white-space:nowrap}
.sc-crm-paid b{float:right;margin-left:.6rem;font-variant-numeric:tabular-nums}
.sc-crm-table-wrap{overflow-x:auto}.sc-home-crm table{width:100%;border-collapse:collapse;font-size:.76rem}
.sc-home-crm caption{text-align:left;font-size:.72rem;opacity:.75;margin-bottom:.25rem}
.sc-home-crm th,.sc-home-crm td{padding:.3rem .25rem;border-bottom:1px solid #9f875c22;text-align:right;font-variant-numeric:tabular-nums}
.sc-home-crm th:first-child{text-align:left}.sc-home-crm tbody th{font-weight:500}
.sc-home-crm thead th{font-size:.7rem;line-height:1.2}
.sc-crm-status{display:block;margin-top:.45rem;opacity:.8}.sc-crm-coverage{font-size:.7rem;margin-top:.35rem}
.sc-crm-coverage summary{cursor:pointer;font-weight:600}.sc-crm-coverage p{margin:.35rem 0}
</style>"""

JS = """<script>{
const panel=[...document.querySelectorAll(".sc-home-crm")].at(-1);
if(panel&&!panel.dataset.ready){
 panel.dataset.ready="1";
 const select=panel.querySelector("select"), status=panel.querySelector(".sc-crm-status");
 try{const saved=sessionStorage.getItem("homeCRMPeriod");if([...select.options].some(x=>x.value===saved))select.value=saved;}catch{}
 let controller, timer, version=0, attempts=0;
 const fmt=v=>typeof v==="number"&&Number.isFinite(v)?v.toLocaleString():"—";
 function paint(result){
  const data=result.data;
  if(!data){status.textContent=result.state==="unavailable"?"Reporting unavailable · retrying":"Loading verified results…";return;}
  panel.querySelector(".sc-crm-dates").textContent=data.start+" – "+data.end;
  for(const row of panel.querySelectorAll("tbody tr")){
   const values=data.ledger?.rows.find(item=>item.channel===row.dataset.channel);
   for(const cell of row.querySelectorAll("td"))cell.textContent=fmt(values?.[cell.dataset.device]);
  }
  for(const cell of panel.querySelectorAll("[data-roas]")){
   const value=data.roas?.[cell.dataset.roas];
   cell.textContent=typeof value==="number"&&Number.isFinite(value)?value.toFixed(2)+"×":"—";
  }
  const ledger=data.ledger;
  const stamp=new Intl.DateTimeFormat("en-AU",{timeZone:"Australia/Sydney",hour:"2-digit",minute:"2-digit"}).format(new Date(data.checked_at));
  const coverage=Object.entries(data.coverage||{}).map(([source,item])=>source+": "+item.status+(item.fetched_at?" · "+item.fetched_at:""));
  panel.querySelector(".sc-crm-sources").textContent=coverage.join(" | ");
  panel.querySelector(".sc-crm-basis").textContent=data.basis;
  let note=ledger?ledger.orders+" Shopify orders · "+ledger.matched+" exact GA4 matches · "+ledger.unmatched+" unmatched":"Shopify count unavailable";
  if(data.partial_day)note+=" · Today is partial";
  if(Object.values(data.coverage||{}).some(item=>!["verified","no_delivery"].includes(item.status)))note+=" · Source gaps; see coverage";
  if(result.state!=="ready")note+=" · Refreshing";
  status.textContent=note+" · Checked "+stamp+" Sydney";
 }
 async function load(force=false){
  if(!panel.isConnected)return;
  clearTimeout(timer);controller?.abort();controller=new AbortController();
  const pending=controller,own=++version;const deadline=setTimeout(()=>pending.abort(),15000);
  try{
   const response=await fetch("/ops/meta-morning-brief/results?period="+encodeURIComponent(select.value)+(force?"&refresh=1":""),{signal:pending.signal});
   if(!response.ok)throw Error("Reporting unavailable");
   const result=await response.json();if(own!==version)return;paint(result);
   if(result.state!=="ready"&&attempts++<18)timer=setTimeout(()=>load(),5000);
  }catch{if(own===version){status.textContent="Refresh unavailable · saved values remain dated; retry with Refresh";}}
  finally{clearTimeout(deadline);}
 }
 if(select.value==="yesterday")paint(JSON.parse(panel.dataset.initial));
 select.addEventListener("change",()=>{attempts=0;try{sessionStorage.setItem("homeCRMPeriod",select.value);}catch{}for(const cell of panel.querySelectorAll("tbody td,[data-roas]"))cell.textContent="—";status.textContent="Loading selected period…";panel.querySelector(".sc-crm-dates").textContent="";load();});
 panel.querySelector(".sc-crm-refresh").addEventListener("click",()=>{attempts=0;load(true);});
 load(); // Refresh yesterday too; never leave a missing saved ROAS frozen.
}
}</script>"""


def render(st, today, initial=None):
    st.html(CSS + html(today, initial) + JS, unsafe_allow_javascript=True)
