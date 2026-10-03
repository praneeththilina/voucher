## 2026-09-24 - Interactive Button State Feedback for Single-Row Constraints
**Learning:** In table/list management controls (such as expense line items), keeping a remove button visually enabled when deletion is silently prevented (e.g. `if len(self._rows) <= 1: return`) causes user confusion and poor feedback. Disabling interactive controls when an action is unavailable (`state=tk.DISABLED`) communicates constraints clearly before interaction.
**Action:** Always visually disable action buttons (e.g., delete/remove line buttons) when operating under minimum boundary constraints, and re-enable them dynamically as items are added.

## 2026-09-27 - Master-Detail Auto-Selection on Dialog Load
**Learning:** In master-detail modal dialogs (such as recurring template selectors), leaving list items unselected on initial open forces unnecessary extra clicks and keeps action buttons disabled. Auto-selecting and focusing the first available item on load immediately renders detail previews and enables action buttons for instant keyboard execution (e.g., pressing Enter to apply).
**Action:** Automatically select and focus the first row when populating master-detail treeviews or list views on dialog load, while preserving clear empty-state messaging when no items exist.
