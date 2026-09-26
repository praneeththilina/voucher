## 2025-05-18 - Consolidating Multiple SQLite Stats Queries
**Learning:** Separate `SELECT COUNT(*)` and `SELECT SUM(...)` queries for dashboard statistics on the same table add noticeable SQLite connection query execution overhead. Consolidating multiple filtered counts into a single pass using `CASE WHEN` conditional aggregation reduces query execution overhead by ~33-35%.
**Action:** Always replace multiple `SELECT` count/sum queries targeting the same table and filter conditions with a single conditional aggregation query (`SUM(CASE WHEN ... THEN 1 ELSE 0 END)`).

## 2026-05-18 - SQLite String Sequence Max Aggregation
**Learning:** Querying all matching voucher sequence strings and extracting suffix integers in a Python loop adds significant I/O and CPU overhead as the table grows. Delegating max sequence extraction directly to SQLite using `MAX(CAST(SUBSTR(voucher_number, ?) AS INTEGER))` achieves a ~67-68% speedup in sequence generation time.
**Action:** Use SQLite native string functions (`SUBSTR`, `CAST`) inside `MAX(...)` queries rather than fetching all rows into Python to determine the highest existing sequence counter.

## 2026-05-19 - Reusing Active DB Connections in Sub-Queries
**Learning:** Resolving default configuration settings like `active_company_id` via a separate `get_connection()` call inside DB functions causes a redundant SQLite connection opening and PRAGMA execution roundtrip for every query. Updating setting lookups to accept an optional existing connection (`get_active_company_id(conn)`) reduces sequence generation overhead by ~65%.
**Action:** Always accept an optional `conn=None` parameter in helper functions that query database settings so functions holding an open connection can reuse it.

## 2026-09-26 - Batch Voucher Lookup Replacing N+1 Full Entity Queries
**Learning:** Calling `get_voucher(id)` in a Python loop for multiple selected vouchers executes 5 queries per item (vouchers, line items, attachments, memos, companies) and repeatedly opens/closes database connections, creating a severe N+1 bottleneck (e.g. 50 calls / 250 queries for 25 items). Replacing this with a single `SELECT * FROM vouchers WHERE id IN (...)` query reduces latency from ~147ms to ~2ms (~98.6% speedup).
**Action:** For batch operations (printing, cancelling, deleting), retrieve basic voucher metadata using a single batch query (`get_vouchers_by_ids`) rather than calling individual full entity getters in a loop.

