"""Read-only verification in the configured server environment; never creates an order.

Usage: python scripts/check_prodigi_existing_order.py ALLOCATION_ID [ORDER_ID ITEM_ID]
Prints IDs and capability conclusions only, never keys, URLs or customer details.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from prodigi_client import Client
    from prodigi_preparation import resolve, discover, validate_order
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('allocation_id', type=int)
    parser.add_argument('order_id', nargs='?')
    parser.add_argument('item_id', nargs='?')
    args = parser.parse_args()
    try:
        snapshot = resolve(args.allocation_id)
        client = Client()
        order_id, item_id = ((args.order_id, args.item_id) if args.order_id and args.item_id
                             else discover(snapshot, client))
        order = client.order(order_id)
        validate_order(order, snapshot, order_id, item_id)
        print(f'Exact existing order/item readable: {order_id}/{item_id}; editable draft; one numbered unit.')
        print('No artwork write, order creation, payment or production release performed.')
        print('Imported draft artwork editing still requires a non-production acceptance fixture.')
        return 0
    except ValueError as error:
        print(str(error))
        return 1
    except Exception:
        print('Verification unavailable. Check server configuration; no provider changes were requested.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
