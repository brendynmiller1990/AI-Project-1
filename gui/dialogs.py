from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
    QLineEdit, QCheckBox, QDialogButtonBox, QFormLayout
)


class ErrorDialog(QDialog):
    def __init__(self, title: str, message: str, diagnostic: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(680)

        layout = QVBoxLayout(self)

        msg = QLabel(message)
        msg.setWordWrap(True)
        layout.addWidget(msg)

        self.diag = QTextEdit()
        self.diag.setReadOnly(True)
        self.diag.setVisible(False)
        self.diag.setPlainText(diagnostic or "")
        self.diag.setMinimumHeight(260)

        toggle_btn = QPushButton("Show details")
        toggle_btn.clicked.connect(self._toggle_details)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(self.accept)

        row = QHBoxLayout()
        row.addWidget(toggle_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        row.addStretch(1)
        layout.addLayout(row)

        layout.addWidget(self.diag)
        layout.addWidget(btns)

        self._toggle_btn = toggle_btn

    def _toggle_details(self):
        visible = not self.diag.isVisible()
        self.diag.setVisible(visible)
        self._toggle_btn.setText("Hide details" if visible else "Show details")


@dataclass(frozen=True)
class CreateProjectResult:
    project_name: str
    topic_prompt: str
    notes: str | None
    sources: tuple[str, ...]


class CreateProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Project")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("lowercase snake_case, e.g. bladder_smc_strain")

        self.topic_edit = QTextEdit()
        self.topic_edit.setPlaceholderText("Describe the topic prompt...")
        self.topic_edit.setMinimumHeight(110)

        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("Optional notes")
        self.notes_edit.setMinimumHeight(80)

        self.cb_pmc = QCheckBox("PMC (open access)")
        self.cb_biorxiv = QCheckBox("bioRxiv (open access)")
        self.cb_pmc.setChecked(True)
        self.cb_biorxiv.setChecked(True)

        form.addRow("Project name:", self.name_edit)
        form.addRow("Topic prompt:", self.topic_edit)
        form.addRow("Notes (optional):", self.notes_edit)

        sources_row = QHBoxLayout()
        sources_row.addWidget(self.cb_pmc)
        sources_row.addWidget(self.cb_biorxiv)
        sources_row.addStretch(1)
        form.addRow("Sources:", sources_row)

        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Create")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)


    def get_result(self) -> CreateProjectResult:
        name = self.name_edit.text().strip()
        topic = self.topic_edit.toPlainText().strip()
        notes = self.notes_edit.toPlainText().strip() or None

        sources = []
        if self.cb_pmc.isChecked():
            sources.append("pmc")
        if self.cb_biorxiv.isChecked():
            sources.append("biorxiv")

        return CreateProjectResult(
            project_name=name,
            topic_prompt=topic,
            notes=notes,
            sources=tuple(sources),
        )
