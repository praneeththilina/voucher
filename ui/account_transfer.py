"""Full-page banking workspace for inter-account and credit-card transfers."""

from datetime import date
import tkinter as tk
from tkinter import messagebox

import ttkbootstrap as tb
from ttkbootstrap.constants import BOTH, END, LEFT, RIGHT, W, X

import database as db


class AccountTransferFrame(tb.Frame):
    """Post balanced transfers between cash, bank, and card ledgers."""

    def __init__(self, parent, company_id=None, on_saved=None, on_close=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.on_saved = on_saved
        self.on_close = on_close
        self._accounts = []
        self._account_map = {}
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = tb.Frame(self, padding=18)
        root.pack(fill=BOTH, expand=True)

        header = tb.Frame(root)
        header.pack(fill=X, pady=(0, 18))
        title = tb.Frame(header)
        title.pack(side=LEFT)
        tb.Label(
            title, text="Banking Transfer", font=("Segoe UI", 17, "bold")
        ).pack(anchor=W)
        tb.Label(
            title,
            text=(
                "Move money between company ledgers or pay a business credit "
                "card with a balanced journal entry."
            ),
            bootstyle="secondary",
        ).pack(anchor=W)
        tb.Button(
            header, text="← Back", bootstyle="secondary-outline",
            command=self._close,
        ).pack(side=RIGHT)

        card = tb.Labelframe(root, text="Transfer details", padding=18)
        card.pack(fill=X)
        card.columnconfigure(1, weight=1)

        self.kind_var = tk.StringVar(value="Inter-account transfer")
        self.date_var = tk.StringVar(value=date.today().isoformat())
        self.from_var = tk.StringVar()
        self.to_var = tk.StringVar()
        self.amount_var = tk.StringVar()
        self.rate_var = tk.StringVar(value="1.000000")
        self.reference_var = tk.StringVar()
        self.memo_var = tk.StringVar()

        labels = (
            ("Transaction type", self.kind_var),
            ("Transfer date", self.date_var),
            ("From account", self.from_var),
            ("To account", self.to_var),
            ("Amount", self.amount_var),
            ("Reference", self.reference_var),
            ("Memo", self.memo_var),
        )
        for row, (label, variable) in enumerate(labels):
            tb.Label(card, text=f"{label}:", font=("Segoe UI", 9, "bold")).grid(
                row=row, column=0, sticky=W, padx=(0, 12), pady=7
            )
            if row == 0:
                widget = tb.Combobox(
                    card, textvariable=variable,
                    values=("Inter-account transfer", "Credit card payment"),
                    state="readonly", width=58,
                )
                widget.bind("<<ComboboxSelected>>", self._on_kind_changed)
            elif row in (2, 3):
                widget = tb.Combobox(
                    card, textvariable=variable, state="readonly", width=58
                )
                if row == 2:
                    self.from_combo = widget
                    widget.bind("<<ComboboxSelected>>", self._on_kind_changed)
                else:
                    self.to_combo = widget
            else:
                widget = tb.Entry(card, textvariable=variable, width=61)
            widget.grid(row=row, column=1, sticky="ew", pady=7)

        self.help_label = tb.Label(
            card,
            text="Debit the receiving account and credit the paying account.",
            bootstyle="info",
        )
        self.help_label.grid(row=8, column=1, sticky=W, pady=(5, 0))

        actions = tb.Frame(root)
        actions.pack(fill=X, pady=(16, 0))
        tb.Button(
            actions, text="Post transfer", bootstyle="success",
            command=self._post,
        ).pack(side=RIGHT)
        tb.Button(
            actions, text="Clear", bootstyle="secondary-outline",
            command=self._clear,
        ).pack(side=RIGHT, padx=(0, 8))

        audit = tb.Labelframe(root, text="Accounting treatment", padding=14)
        audit.pack(fill=X, pady=(18, 0))
        tb.Label(
            audit,
            text=(
                "Inter-account transfer: Dr destination / Cr source.  "
                "Credit-card payment: Dr credit-card liability / Cr cash or bank.  "
                "No income or expense is created."
            ),
            wraplength=900,
            justify=LEFT,
        ).pack(anchor=W)

    def refresh(self):
        """Reload eligible active monetary accounts."""
        rows = db.get_chart_of_accounts(
            company_id=self.company_id, active_only=True
        )
        self._accounts = [
            row for row in rows
            if row.get("account_type") in {"Asset", "Liability"}
            and any(
                token in (
                    f"{row.get('account_name', '')} "
                    f"{row.get('detail_type', '')} "
                    f"{row.get('sub_category', '')}"
                ).lower()
                for token in ("cash", "bank", "card", "wallet")
            )
        ]
        self._account_map = {
            self._label(row): row for row in self._accounts
        }
        self._on_kind_changed()

    @staticmethod
    def _label(account):
        currency = (account.get("currency") or "LKR").upper()
        return (
            f"[{account['account_code']}] {account['account_name']} "
            f"— {currency}"
        )

    def _on_kind_changed(self, _event=None):
        card_payment = self.kind_var.get() == "Credit card payment"
        source = [
            self._label(row) for row in self._accounts
            if row.get("account_type") == "Asset"
        ]
        if card_payment:
            target = [
                self._label(row) for row in self._accounts
                if row.get("account_type") == "Liability"
                and "card" in (
                    f"{row.get('account_name', '')} "
                    f"{row.get('detail_type', '')} "
                    f"{row.get('sub_category', '')}"
                ).lower()
            ]
            self.help_label.configure(
                text="Pays down the selected card: debit card liability, credit bank/cash."
            )
        else:
            target = [self._label(row) for row in self._accounts]
            self.help_label.configure(
                text="Moves funds without changing profit: debit destination, credit source."
            )
        self.from_combo.configure(values=source)
        self.to_combo.configure(values=target)
        if self.from_var.get() not in source:
            self.from_var.set(source[0] if source else "")
        if self.to_var.get() not in target:
            self.to_var.set(target[0] if target else "")
        selected = self._account_map.get(self.from_var.get())
        currency = (selected.get("currency") if selected else None) or db.get_company_base_currency(self.company_id)
        home = db.get_company_base_currency(self.company_id)
        rate_row = db.get_exchange_rate(currency, home, self.date_var.get().strip())
        self.rate_var.set(f"{float(rate_row.get('rate', 1.0)):0.6f}" if rate_row else "1.000000")

    def _clear(self):
        self.date_var.set(date.today().isoformat())
        self.amount_var.set("")
        self.rate_var.set("1.000000")
        self.reference_var.set("")
        self.memo_var.set("")

    def _post(self):
        source = self._account_map.get(self.from_var.get())
        target = self._account_map.get(self.to_var.get())
        if not source or not target:
            messagebox.showwarning(
                "Select accounts", "Select both a paying and receiving account.",
                parent=self,
            )
            return
        if source["id"] == target["id"]:
            messagebox.showwarning(
                "Same account", "From and To accounts must be different.", parent=self
            )
            return
        source_currency = (source.get("currency") or "LKR").upper()
        target_currency = (target.get("currency") or "LKR").upper()
        if source_currency != target_currency:
            messagebox.showwarning(
                "Currency mismatch",
                "Transfers require accounts in the same currency. Use a foreign-exchange journal for conversion.",
                parent=self,
            )
            return
        try:
            amount = round(float(self.amount_var.get().replace(",", "")), 2)
        except ValueError:
            amount = 0.0
        if amount <= 0:
            messagebox.showwarning(
                "Invalid amount", "Enter a transfer amount greater than zero.", parent=self
            )
            return
        try:
            entry_id = db.create_account_transfer(
                company_id=self.company_id,
                transfer_date=self.date_var.get().strip(),
                source_account_id=source["id"],
                target_account_id=target["id"],
                amount=amount,
                exchange_rate=float(self.rate_var.get() or 1.0),
                reference=self.reference_var.get().strip(),
                memo=self.memo_var.get().strip(),
                transfer_type=(
                    "credit_card_payment"
                    if self.kind_var.get() == "Credit card payment"
                    else "account_transfer"
                ),
            )
            messagebox.showinfo(
                "Transfer posted",
                f"Journal entry #{entry_id} posted for {source_currency} {amount:,.2f}.",
                parent=self,
            )
            self._clear()
            if self.on_saved:
                self.on_saved()
        except Exception as exc:
            messagebox.showerror("Transfer failed", str(exc), parent=self)

    def _close(self):
        if self.on_close:
            self.on_close()