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

## 2026-09-27 - Batch Line Item Retrieval in Money Float Ledger
**Learning:** In `get_float_ledger`, executing `SELECT description, category, amount FROM line_items WHERE voucher_id = ?` individually in a Python loop for every active voucher belonging to a money float creates an N+1 query loop. Replacing individual queries with a single batched `WHERE voucher_id IN (...)` query and grouping in Python (`collections.defaultdict(list)`) eliminates N query overhead and yields up to ~98% latency reduction in line item fetching.
**Action:** When building ledger or summary views that require line items for multiple vouchers, batch fetch all related line items in a single query using `WHERE voucher_id IN (...)` instead of executing a subquery inside the voucher iteration loop.

## 2026-09-28 - Batch Line Item Retrieval in CSV Voucher Exports
**Learning:** In `export_vouchers_to_csv`, executing individual `SELECT ... FROM line_items WHERE voucher_id = ?` queries per voucher in a loop created an N+1 query loop across all export formats (`itemized`, `register`, `category_summary`, `summary`). Pre-fetching all line items in a single chunked `WHERE voucher_id IN (...)` query and mapping them via `collections.defaultdict(list)` in Python reduces query count from N to 1 and eliminates N query overhead during CSV exports.
**Action:** Whenever exporting or formatting multi-record models with child line items, pre-fetch child records using batched `WHERE parent_id IN (...)` queries chunked to stay within parameter limits rather than querying child records inside iteration loops.

## 2026-09-29 - Consolidated Single Pass Money Float Balance Query
**Learning:** In `get_floats`, executing 3 separate SQLite subqueries (`Inflow`, `Outflow`, `vouchers`) inside a Python loop for each money float generated $1 + 3M$ queries per call. Replacing the loop subqueries with a single query using grouped `LEFT JOIN` subqueries and conditional aggregation (`SUM(CASE WHEN ... THEN amount ELSE 0 END)`) reduces database queries to 1 and delivers a ~46% latency reduction per call.
**Action:** Consolidate per-parent item aggregate subqueries in parent-child models into grouped `LEFT JOIN` subqueries with conditional aggregation instead of querying child aggregates in Python iteration loops.

## 2026-09-30 - Batched Full Entity Retrieval for PDF Generation
**Learning:** In `generate_voucher_pdf`, calling `db.get_voucher(vid)` and `db.get_attachment_data(att['id'])` in a loop for each selected voucher executed $5N + M$ database queries (vouchers, line items, attachments, memos, companies, plus attachment re-fetches). Implementing `db.get_vouchers_full_by_ids` to batch-fetch all parent and child records using chunked `WHERE IN (...)` queries reduces query count by ~96.7% (from 120 queries down to 4 queries for 20 items) and speeds up data fetching by ~60%.
**Action:** For document generation or batch processing needing full composite entity models (with line items, attachments, companies), use chunked `WHERE parent_id IN (...)` queries to batch fetch all composite records in a fixed number of queries.

## 2026-10-01 - Reusing SQLite Connections Across UI Refresh Pipelines
**Learning:** Calling separate DB functions during UI list refreshes (`get_floats`, `search_vouchers`, `get_voucher_stats`, `get_company`) repeatedly opens/closes database connections and executes `PRAGMA foreign_keys = ON` roundtrips. Passing an optional `conn` parameter to allow functions to reuse a single open connection across the refresh pipeline reduces connection setup latency and improves search/refresh responsiveness.
**Action:** Always accept an optional `conn=None` parameter in database search and aggregate functions so complex UI refresh pipelines can reuse an active connection.

## 2026-10-02 - Consolidating Audit Lookups & Batching Status Updates
**Learning:** In audit logging and status updates, running separate `SELECT company_id` and `SELECT prepared_by` queries on `vouchers` for every event doubles database query overhead. Combining consecutive lookup queries into a single multi-column SELECT (`SELECT company_id, prepared_by`) and batching `mark_as_printed` updates with chunked `WHERE id IN (...)` queries eliminates redundant queries during batch actions.
**Action:** Always combine multi-attribute lookup SELECT queries on the same record into a single SELECT statement and batch status updates across list items using chunked `WHERE id IN (...)` queries.

## 2026-10-03 - Pre-Aggregating Child Counts in Parent Entity Queries
**Learning:** In template and master-detail dialogs, calling `get_template(t['id'])` in a loop to get child line item counts executes $1 + 2N$ SQL queries and opens $1 + N$ database connections. Pre-aggregating line item counts directly in `get_templates` using `SELECT vt.*, COUNT(tli.id) AS item_count ... LEFT JOIN ... GROUP BY vt.id` reduces query count to 1 and connection overhead to 1 (~95-98% latency reduction).
**Action:** When populating list views or treeviews that only need child record counts, pre-aggregate child counts directly in the parent list query using `LEFT JOIN` and `COUNT(child.id)` rather than fetching full child entities in an N+1 loop.

## 2026-10-04 - Single Pass Budget Lookup & Spending Sum Consolidation
**Learning:** In `check_category_budget_alert`, executing separate queries for category budget lookup and line item spend aggregation added an extra database query roundtrip per alert check. Combining the budget lookup via a scalar subquery and the active line item spending sum into a single SQL statement eliminates the extra query roundtrip while preserving 100% of the return dictionary structure.
**Action:** When validating multi-table constraints (such as budgets vs actual spend), combine scalar configuration lookups and aggregate calculations into a single SELECT statement.

## 2026-10-04 - Consolidated Single Pass Query for Individual Money Float Balance
**Learning:** In `get_float`, executing 4 separate SQLite queries (`money_floats`, inflow sum, outflow sum, voucher count/sum) for a single float record added ~46% query latency overhead. Consolidating into a single SQL pass with grouped `LEFT JOIN` subqueries and conditional aggregation reduces query executions from 4 to 1 while preserving all returned fields and dictionary keys.
**Action:** Always consolidate aggregate subqueries on single parent entities into a unified `LEFT JOIN` query instead of issuing multiple sequential queries.

## 2026-10-04 - Connection Reuse and Cached Company Lookups in Voucher Number Generation
**Learning:** `get_next_voucher_number` and `preview_next_voucher_number` repeatedly opened fresh SQLite connections and executed direct SQL table queries on `companies` without checking `_CACHE["companies"]`. Supporting an optional `conn=None` parameter and reusing `get_company(company_id, conn=conn)` eliminated redundant connection initialization and company table lookups, yielding an ~88.6% reduction in sequence generation latency (from ~863ms down to ~99ms for 500 calls).
**Action:** Helper and sequence generator functions that inspect company configuration must accept an optional `conn=None` parameter and query through cached lookups (`get_company`) rather than opening new connections or issuing raw `SELECT * FROM companies` statements.

## 2026-10-04 - Batch Due Date Updating Replacing Full Entity Mutation Loops
**Learning:** In the UI batch action for setting or clearing due dates across selected vouchers, looping over `get_voucher(id)` followed by `update_voucher(id, v, items)` executed ~17 database queries per voucher (re-fetching all attachments, memos, and tags, deleting and re-inserting all line items, re-upserting categories and payees, and writing separate audit logs). Replacing this loop with `update_due_dates_batch` (chunked `UPDATE vouchers SET due_date = ...` and batched audit logging) reduced latency from ~2766ms down to ~123ms for 20 items (~95.6% speedup).
**Action:** When updating single metadata fields (like due date, status, or flags) across multiple selected records, execute chunked direct column UPDATEs and batch audit logging instead of reading and rewriting complete composite entity structures.
