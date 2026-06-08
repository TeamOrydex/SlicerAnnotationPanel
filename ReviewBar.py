import qt
from datetime import datetime


class ReviewBar(qt.QWidget):
    """
    Reviewer controls: Approve / Reject with comments.
    Intended to be shown only in reviewer mode.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._on_approve_callback = None
        self._on_reject_callback = None
        self._setup_ui()

    def _setup_ui(self):
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._review_info_label = qt.QLabel("")
        self._review_info_label.setStyleSheet("color: #666; font-style: italic;")
        self._review_info_label.setWordWrap(True)
        self._review_info_label.hide()
        layout.addWidget(self._review_info_label)

        btn_row = qt.QHBoxLayout()
        self._approve_btn = qt.QPushButton("Approve")
        self._approve_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "padding: 6px 16px; border-radius: 3px; }"
            "QPushButton:hover { background-color: #45a049; }"
        )
        self._approve_btn.clicked.connect(self._handle_approve)
        btn_row.addWidget(self._approve_btn)

        self._reject_btn = qt.QPushButton("Reject")
        self._reject_btn.setStyleSheet(
            "QPushButton { background-color: #f44336; color: white; "
            "padding: 6px 16px; border-radius: 3px; }"
            "QPushButton:hover { background-color: #da190b; }"
        )
        self._reject_btn.clicked.connect(self._show_reject_area)
        btn_row.addWidget(self._reject_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._reject_area = qt.QWidget()
        reject_layout = qt.QVBoxLayout(self._reject_area)
        reject_layout.setContentsMargins(0, 8, 0, 0)

        reject_layout.addWidget(qt.QLabel("Rejection comments:"))
        self._comments_edit = qt.QTextEdit()
        self._comments_edit.setMaximumHeight(80)
        self._comments_edit.setPlaceholderText("Explain why this annotation is being rejected...")
        reject_layout.addWidget(self._comments_edit)

        self._confirm_reject_btn = qt.QPushButton("Confirm Reject")
        self._confirm_reject_btn.setStyleSheet(
            "QPushButton { background-color: #f44336; color: white; "
            "padding: 4px 12px; border-radius: 3px; }"
        )
        self._confirm_reject_btn.clicked.connect(self._handle_reject)
        reject_layout.addWidget(self._confirm_reject_btn)

        self._reject_area.hide()
        layout.addWidget(self._reject_area)

    def set_callbacks(self, on_approve=None, on_reject=None):
        self._on_approve_callback = on_approve
        self._on_reject_callback = on_reject

    def _handle_approve(self):
        if self._on_approve_callback:
            self._on_approve_callback()

    def _show_reject_area(self):
        self._reject_area.show()

    def _handle_reject(self):
        comments = self._comments_edit.plainText.strip()
        if self._on_reject_callback:
            self._on_reject_callback(comments)
        self._reject_area.hide()
        self._comments_edit.clear()

    def show_review_info(self, record):
        """Display previous review information if available."""
        if record.reviewed_by:
            if record.status == "approved":
                text = f"Reviewed by {record.reviewed_by} on {record.reviewed_at}: Approved"
            elif record.status == "rejected":
                text = f"Rejected by {record.reviewed_by} on {record.reviewed_at}"
                if record.review_comments:
                    text += f"\nComments: {record.review_comments}"
            else:
                text = ""
            self._review_info_label.setText(text)
            self._review_info_label.show()
        else:
            self._review_info_label.hide()

    def set_enabled(self, enabled):
        self._approve_btn.setEnabled(enabled)
        self._reject_btn.setEnabled(enabled)
        self._confirm_reject_btn.setEnabled(enabled)
        self._comments_edit.setEnabled(enabled)
