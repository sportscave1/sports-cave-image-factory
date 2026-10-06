"""Preview first; --apply explicitly allocates one exact paid order line."""
import argparse
import json
from edition_order_recovery import preview, allocate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--order', required=True)
    parser.add_argument('--line', required=True)
    parser.add_argument('--product', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expected-next', type=int)
    parser.add_argument('--confirm-mapping', default='')
    args = parser.parse_args()
    if args.apply:
        if args.expected_next is None:
            parser.error('--expected-next must come from a reviewed preview')
        result = allocate(args.order, args.line, args.product, confirmation=args.confirm_mapping, expected_next=args.expected_next)
        # Do not print customer/email fields from allocator records.
        print(json.dumps({k: v for k, v in result.items() if k not in ('allocations', 'mirror')}, default=str))
        print(json.dumps({'editions': [r['edition_number'] for r in result['allocations']],
                          'mirror_errors': bool(result['mirror'].get('errors'))}))
    else:
        print(json.dumps(preview(args.order, args.line, args.product), default=str, indent=2))


if __name__ == '__main__':
    main()
