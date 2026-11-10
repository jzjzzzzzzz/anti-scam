# Data handling and limitations

## Application records

- Recipient email, optional label, enabled/authorization state and administrator ID.
- Campaign name and message content; random bearer link token; creation/expiry times.
- Visit timestamps/counts, per-link first-visit order and email processing states/IDs.

The application does not request passwords or verification codes and does not put
IP addresses or browser fingerprints into visit records. Infrastructure providers
still process requests and may maintain their own operational logs; inspect their
settings before making participant-facing privacy claims.

## Access and retention

The AWS admin API requires an access token in the invited `operators` group.
The existing implementation gives that group access to all campaign/recipient data
in the installation; it is not a multi-tenant per-admin data-isolation system.
Link tokens grant access to disclosure pages without sign-in. Protect them as
bearer URLs and do not include them in public screenshots or repositories.

Link records carry a DynamoDB TTL 90 days after creation, event records 90 days
after the visit. TTL deletion is asynchronous. Link validity (default 30 days,
configurable 1-90) is separate. Recipient records do not auto-expire. Rank counters
retain a hashed scope and count without a TTL to avoid sequence resets. Backups,
exports, captured messages and infrastructure logs need separate retention controls.

Local demos/bridge store SQLite records beside their scripts; they do not apply
AWS TTL behavior. Keep them on loopback and manage their records separately.

## Interpretation

Rank scope is the exact campaign name plus administrator. Reuse that name to share
an order, or choose a new name for a separate exercise. Old first visits predating
the ranking feature are not ranked retroactively. Counts are links, not people;
scanners or forwards may trigger visits. Do not publish individual rankings or
infer an account compromise from a visit.
