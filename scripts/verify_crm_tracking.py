"""Read-only tracking check using the actual Sports Cave OS configuration."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main():
    from crm_shopify import Shopify
    from crm_store import Store
    from crm_tracking_health import verify
    result=verify(Shopify(),Store())
    print(json.dumps(result,indent=2))
    return 0 if result['status']=='READY' else 1

if __name__=='__main__':raise SystemExit(main())
