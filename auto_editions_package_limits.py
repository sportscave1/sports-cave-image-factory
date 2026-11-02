"""Separate HTTP request, disk expansion and generated-asset budgets.

Large packets use the existing durable 8 MiB upload protocol. These ceilings
are disk budgets, not permission to allocate whole packets or larger images.
The existing 95 MP worker and 160 MiB per-image gates still apply.
"""
LEGACY_BYTES = 256 * 1024 * 1024
RESUMABLE_BYTES = 1024 * 1024 * 1024
EXPANDED_BYTES = 1024 * 1024 * 1024
ASSET_BYTES = 160 * 1024 * 1024
DISK_RESERVE = 256 * 1024 * 1024


class PackageBudgetError(ValueError):
    """Retain finished exports; repeating Photoshop cannot fix this boundary."""


def negotiated(protocol, advertised=None):
    # Old servers do not advertise the larger budget. Never infer support from
    # protocol=1 alone: earlier installations accepted only 256 MiB in chunks.
    if protocol == 1 and type(advertised) is int and advertised == RESUMABLE_BYTES:
        return RESUMABLE_BYTES
    return LEGACY_BYTES


def transfer_error(size, limit):
    action = ('A production-accepted resumable backend and compatible Companion are required; '
              'retain this preparation and retry after release acceptance.'
              if limit == LEGACY_BYTES else
              'This preparation exceeds the supported package disk budget; review generated assets.')
    return PackageBudgetError(f'Prepared package is {size} bytes; negotiated transfer limit is {limit} bytes. {action}')
