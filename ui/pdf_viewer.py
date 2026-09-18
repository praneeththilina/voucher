"""
Internal PDF Viewer Dialog
Provides an embedded, high-fidelity PDF viewing popup with page navigation,
zoom controls (100% default zoom), print, external viewer open, and save functions.
"""

import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from PIL import Image, ImageTk

try:
    import pypdfium2 as pdfium
except ImportError:
    pdfium = None

import printer
import database as db


class PdfViewerDialog(tk.Toplevel):
    """
    Embedded PDF viewer modal dialog.
    Renders PDF pages directly inside a scrollable canvas with 100% default zoom.
    """

    # Base scale representing 100% zoom (96 DPI screen scale for 72 pt A4 = 96/72 ≈ 1.333)
    BASE_SCALE = 1.333

    def __init__(self, parent, pdf_path, title="Voucher PDF Preview", voucher_ids=None):
        super().__init__(parent)
        self.title(f"📄 {title}")
        self.geometry("980x820")
        self.minsize(700, 520)
        self.transient(parent)
        self.grab_set()

        self._pdf_path = pdf_path
        self._voucher_ids = voucher_ids or []
        self._doc = None
        self._page_count = 0
        self._current_page = 0
        self._zoom_factor = 1.0  # 1.0 = 100% zoom
        self._photo_cache = None
        self._page_cache = {}  # {(page_idx, round(zoom, 2)): (PhotoImage, w, h)}

        if not os.path.exists(pdf_path):
            messagebox.showerror("Error", f"PDF file not found:\n{pdf_path}", parent=self)
            self.destroy()
            return

        self._load_pdf()
        self._build_ui()
        self._render_current_page()
        self._bind_shortcuts()

        # Center on parent
        self.update_idletasks()
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{px}+{py}")

        self.lift()
        self.focus_force()

    def _load_pdf(self):
        """Open PDF document via pypdfium2."""
        try:
            if pdfium is not None:
                self._doc = pdfium.PdfDocument(self._pdf_path)
                self._page_count = len(self._doc)
            else:
                self._page_count = 0
        except Exception as e:
            messagebox.showerror("PDF Error", f"Could not load PDF document:\n{e}", parent=self)
            self._doc = None
            self._page_count = 0

    def _build_ui(self):
        """Build top toolbar and center scrollable canvas."""
        # ── 1. Top Controls Toolbar (Windows 11 Fluent style) ──────────────
        toolbar = tk.Frame(self, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=12, pady=7)
        toolbar.pack(fill=tk.X)

        # Page Navigation
        nav_box = tk.Frame(toolbar, bg="#ffffff")
        nav_box.pack(side=tk.LEFT)

        self._btn_prev = ttk.Button(
            nav_box, text="◀ Prev", command=self._prev_page,
            bootstyle="secondary-outline", width=7
        )
        self._btn_prev.pack(side=tk.LEFT, padx=(0, 4))

        self._page_lbl = tk.Label(
            nav_box, text=f"Page 1 of {max(1, self._page_count)}",
            font=("Segoe UI", 9, "bold"), bg="#f1f5f9", fg="#0f172a", width=13, padx=4, pady=2
        )
        self._page_lbl.pack(side=tk.LEFT, padx=4)

        self._btn_next = ttk.Button(
            nav_box, text="Next ▶", command=self._next_page,
            bootstyle="secondary-outline", width=7
        )
        self._btn_next.pack(side=tk.LEFT, padx=(4, 12))

        # Separator
        tk.Frame(toolbar, bg="#cbd5e1", width=1, height=24).pack(side=tk.LEFT, padx=4)

        # Zoom Controls
        zoom_box = tk.Frame(toolbar, bg="#ffffff")
        zoom_box.pack(side=tk.LEFT, padx=(10, 0))

        ttk.Button(
            zoom_box, text="🔍 -", command=self._zoom_out,
            bootstyle="secondary-outline", width=4
        ).pack(side=tk.LEFT, padx=2)

        self._zoom_lbl = tk.Label(
            zoom_box, text="100%",
            font=("Segoe UI", 9, "bold"), bg="#f0f9ff", fg="#0369a1", width=6, padx=2, pady=2
        )
        self._zoom_lbl.pack(side=tk.LEFT, padx=2)

        ttk.Button(
            zoom_box, text="🔍 +", command=self._zoom_in,
            bootstyle="secondary-outline", width=4
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            zoom_box, text="100%", command=self._zoom_reset,
            bootstyle="info-outline", width=5
        ).pack(side=tk.LEFT, padx=(4, 2))

        ttk.Button(
            zoom_box, text="Fit Width", command=self._zoom_fit_width,
            bootstyle="secondary-outline", width=8
        ).pack(side=tk.LEFT, padx=2)

        # Right Action Buttons
        act_box = tk.Frame(toolbar, bg="#ffffff")
        act_box.pack(side=tk.RIGHT)

        ttk.Button(
            act_box, text="🖨️ Print", command=self._print_pdf,
            bootstyle="success", width=9
        ).pack(side=tk.LEFT, padx=3)

        ttk.Button(
            act_box, text="↗ Open in External App", command=self._open_external,
            bootstyle="primary-outline", width=20
        ).pack(side=tk.LEFT, padx=3)

        ttk.Button(
            act_box, text="💾 Save Copy", command=self._save_copy,
            bootstyle="secondary-outline", width=11
        ).pack(side=tk.LEFT, padx=3)

        ttk.Button(
            act_box, text="✕ Close", command=self.destroy,
            bootstyle="danger-outline", width=7
        ).pack(side=tk.LEFT, padx=(6, 0))

        # ── 2. Canvas with Double Scrollbars ───────────────────────────────
        canvas_frame = tk.Frame(self, bg="#475569")
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self._canvas = tk.Canvas(canvas_frame, bg="#475569", highlightthickness=0)
        self._v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self._canvas.yview)
        self._h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self._canvas.xview)

        self._canvas.configure(xscrollcommand=self._h_scroll.set, yscrollcommand=self._v_scroll.set)

        self._v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _bind_shortcuts(self):
        """Keyboard navigation and mouse wheel scrolling/zooming."""
        self.bind("<Escape>", lambda e: (self.destroy(), "break")[1])
        self.bind("<Left>", lambda e: self._prev_page())
        self.bind("<Right>", lambda e: self._next_page())
        self.bind("<Prior>", lambda e: self._prev_page())   # Page Up
        self.bind("<Next>", lambda e: self._next_page())    # Page Down
        self.bind("<plus>", lambda e: self._zoom_in())
        self.bind("<equal>", lambda e: self._zoom_in())
        self.bind("<minus>", lambda e: self._zoom_out())
        self.bind("<Control-0>", lambda e: self._zoom_reset())
        self.bind("<Control-p>", lambda e: self._print_pdf())
        self.bind("<Control-P>", lambda e: self._print_pdf())
        self.bind("<Control-o>", lambda e: self._open_external())
        self.bind("<Control-O>", lambda e: self._open_external())

        # Mouse wheel events
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind("<Shift-MouseWheel>", self._on_shift_mousewheel)
        self._canvas.bind("<Control-MouseWheel>", self._on_ctrl_mousewheel)

    def _render_current_page(self):
        """Render the current page image onto the canvas at current zoom level with caching."""
        if not self._doc or self._page_count == 0:
            self._canvas.delete("all")
            self._canvas.create_text(
                350, 200, text="No pages available or PDF preview unavailable.",
                fill="#cbd5e1", font=("Segoe UI", 12)
            )
            return

        try:
            cache_key = (self._current_page, round(self._zoom_factor, 2))
            if cache_key in self._page_cache:
                self._photo_cache, img_w, img_h = self._page_cache[cache_key]
            else:
                page = self._doc[self._current_page]
                render_scale = self.BASE_SCALE * self._zoom_factor
                pil_img = page.render(scale=render_scale).to_pil()
                self._photo_cache = ImageTk.PhotoImage(pil_img)
                img_w, img_h = pil_img.size
                if len(self._page_cache) > 20:
                    self._page_cache.pop(next(iter(self._page_cache)))
                self._page_cache[cache_key] = (self._photo_cache, img_w, img_h)

            self._canvas.delete("all")
            c_w = max(self._canvas.winfo_width(), 100)
            c_h = max(self._canvas.winfo_height(), 100)

            pad = 20
            total_w = max(img_w + 2 * pad, c_w)
            total_h = max(img_h + 2 * pad, c_h)

            x_pos = max(pad, (total_w - img_w) // 2)
            y_pos = pad

            # Subtle drop shadow behind page
            self._canvas.create_rectangle(
                x_pos - 2, y_pos - 2, x_pos + img_w + 3, y_pos + img_h + 3,
                fill="#1e293b", outline="#0f172a", width=1
            )
            self._canvas.create_image(x_pos, y_pos, anchor="nw", image=self._photo_cache)

            # Set scroll region
            self._canvas.configure(scrollregion=(0, 0, total_w, y_pos + img_h + pad))

            # Update UI labels & buttons
            self._page_lbl.config(text=f"Page {self._current_page + 1} of {self._page_count}")
            self._zoom_lbl.config(text=f"{int(self._zoom_factor * 100)}%")
            self._btn_prev.configure(state="normal" if self._current_page > 0 else "disabled")
            self._btn_next.configure(state="normal" if self._current_page < self._page_count - 1 else "disabled")

        except Exception as e:
            self._canvas.delete("all")
            self._canvas.create_text(
                350, 200, text=f"Error rendering page:\n{e}",
                fill="#ef4444", font=("Segoe UI", 11)
            )

    # ── Page Navigation ────────────────────────────────────────────────────

    def _prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._render_current_page()
            self._canvas.yview_moveto(0)

    def _next_page(self):
        if self._current_page < self._page_count - 1:
            self._current_page += 1
            self._render_current_page()
            self._canvas.yview_moveto(0)

    # ── Zoom Controls ──────────────────────────────────────────────────────

    def _zoom_in(self):
        if self._zoom_factor < 2.5:
            self._zoom_factor = round(self._zoom_factor + 0.15, 2)
            self._render_current_page()

    def _zoom_out(self):
        if self._zoom_factor > 0.4:
            self._zoom_factor = round(self._zoom_factor - 0.15, 2)
            self._render_current_page()

    def _zoom_reset(self):
        """Reset to 100% zoom."""
        self._zoom_factor = 1.0
        self._render_current_page()

    def _zoom_fit_width(self):
        """Scale image to fit the visible canvas width."""
        c_w = self._canvas.winfo_width()
        if c_w > 100 and self._doc and self._page_count > 0:
            try:
                page = self._doc[self._current_page]
                # Page width in points (standard A4 is 595.27 pt)
                pw, _ = page.get_size()
                # Target pixel width with 40px padding
                target_w = max(200, c_w - 40)
                # target_w = pw * (BASE_SCALE * zoom_factor)
                needed_zoom = target_w / (pw * self.BASE_SCALE)
                self._zoom_factor = max(0.4, min(2.5, round(needed_zoom, 2)))
                self._render_current_page()
            except Exception:
                pass

    # ── Mouse Wheel Handlers ───────────────────────────────────────────────

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_shift_mousewheel(self, event):
        self._canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_ctrl_mousewheel(self, event):
        if event.delta > 0:
            self._zoom_in()
        else:
            self._zoom_out()

    # ── Action Buttons ─────────────────────────────────────────────────────

    def _print_pdf(self):
        """Send PDF directly to Windows default printer."""
        try:
            success = printer.print_pdf(self._pdf_path)
            if success:
                if self._voucher_ids:
                    db.mark_as_printed(self._voucher_ids)
                messagebox.showinfo("Printing", "Document sent to default Windows printer.", parent=self)
            else:
                messagebox.showwarning("Print", "Could not send to printer automatically.", parent=self)
        except Exception as e:
            messagebox.showerror("Print Error", f"Error printing PDF:\n{e}", parent=self)

    def _open_external(self):
        """Open PDF in external system PDF viewer (Acrobat, Browser, etc.)."""
        try:
            printer.open_pdf(self._pdf_path)
        except Exception as e:
            messagebox.showerror("Open Error", f"Could not open external viewer:\n{e}", parent=self)

    def _save_copy(self):
        """Save a copy of the PDF to a user-chosen destination."""
        default_name = os.path.basename(self._pdf_path)
        dest = filedialog.asksaveasfilename(
            parent=self,
            title="Save PDF Copy As",
            initialfile=default_name,
            defaultextension=".pdf",
            filetypes=[("PDF Documents", "*.pdf"), ("All Files", "*.*")]
        )
        if dest:
            try:
                shutil.copy2(self._pdf_path, dest)
                messagebox.showinfo("Saved", f"PDF saved successfully to:\n{dest}", parent=self)
            except Exception as e:
                messagebox.showerror("Save Error", f"Could not save copy:\n{e}", parent=self)
