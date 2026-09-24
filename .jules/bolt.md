## 2025-05-18 - Consolidating Multiple SQLite Stats Queries
**Learning:** Separate `SELECT COUNT(*)` and `SELECT SUM(...)` queries for dashboard statistics on the same table add noticeable SQLite connection query execution overhead. Consolidating multiple filtered counts into a single pass using `CASE WHEN` conditional aggregation reduces query execution overhead by ~33-35%.
**Action:** Always replace multiple `SELECT` count/sum queries targeting the same table and filter conditions with a single conditional aggregation query (`SUM(CASE WHEN ... THEN 1 ELSE 0 END)`).

## 2026-05-18 - SQLite String Sequence Max Aggregation
**Learning:** Querying all matching voucher sequence strings and extracting suffix integers in a Python loop adds significant I/O and CPU overhead as the table grows. Delegating max sequence extraction directly to SQLite using `MAX(CAST(SUBSTR(voucher_number, ?) AS INTEGER))` achieves a ~67-68% speedup in sequence generation time.
**Action:** Use SQLite native string functions (`SUBSTR`, `CAST`) inside `MAX(...)` queries rather than fetching all rows into Python to determine the highest existing sequence counter.
