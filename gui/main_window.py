from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QFileDialog, QHeaderView
)

from project_creator import (
    ProjectConfig,
    create_project,
    list_projects,
    open_project,
    ProjectCreatorError,
    ProjectOpenError,
)
from project_overview.canonical_schema import CANONICAL_SCHEMA_SQL, EXPECTED_SCHEMA

from gui.dialogs import CreateProjectDialog, ErrorDialog


class MainWindow(QMainWindow):
    def __init__(self, base_projects_dir: Path):
        super().__init__()
        self.setWindowTitle("AI Project 1 — Project Workspace")
        self.resize(1000, 640)

        self.base_projects_dir = base_projects_dir.resolve()
        self.current_project_dir: Path | None = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        # Top bar
        top = QHBoxLayout()
        self.base_dir_label = QLabel(f"Base projects dir: {self.base_projects_dir}")
        self.base_dir_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        btn_change_base = QPushButton("Change…")
        btn_change_base.clicked.connect(self.on_change_base_dir)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.refresh_projects)

        btn_create = QPushButton("Create Project…")
        btn_create.clicked.connect(self.on_create_project)

        btn_open = QPushButton("Open Selected")
        btn_open.clicked.connect(self.on_open_selected)

        top.addWidget(self.base_dir_label, stretch=1)
        top.addWidget(btn_change_base)
        top.addWidget(btn_refresh)
        top.addWidget(btn_create)
        top.addWidget(btn_open)
        layout.addLayout(top)

        # Current project banner
        self.current_label = QLabel("Current project: (none)")
        self.current_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.current_label)

        # Projects table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Valid", "Project ID", "Name", "Created", "Topic", "Dir"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(self.table.SelectionMode.SingleSelection)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, stretch=1)

        self.refresh_projects()

    # ---------- UI actions ----------

    def on_change_base_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select base projects directory", str(self.base_projects_dir))
        if not d:
            return
        self.base_projects_dir = Path(d).resolve()
        self.base_dir_label.setText(f"Base projects dir: {self.base_projects_dir}")
        self.refresh_projects()

    def on_create_project(self):
        dlg = CreateProjectDialog(self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        r = dlg.get_result()

        cfg = ProjectConfig(
            project_name=r.project_name,
            topic_prompt=r.topic_prompt,
            base_projects_dir=self.base_projects_dir,
            citation_style="vancouver",
            sources=r.sources,
            notes=r.notes,
        )

        try:
            info = create_project(cfg, expected_schema=EXPECTED_SCHEMA, canonical_schema_sql=CANONICAL_SCHEMA_SQL)
            self.current_project_dir = info.project_dir
            self.current_label.setText(f"Current project: {info.project_id}  ({info.project_dir})")
            self.refresh_projects(select_project_id=info.project_id)
        except ProjectCreatorError as e:
            ErrorDialog("Create failed", e.message, e.diagnostic, parent=self).exec()

    def on_open_selected(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return
        row = sel[0].row()
        project_dir_str = self.table.item(row, 5).text()
        project_dir = Path(project_dir_str)

        try:
            info = open_project(project_dir, expected_schema=EXPECTED_SCHEMA, canonical_schema_sql=CANONICAL_SCHEMA_SQL)
            self.current_project_dir = info.project_dir
            self.current_label.setText(f"Current project: {info.project_id}  ({info.project_dir})")
        except ProjectCreatorError as e:
            ErrorDialog("Open failed", e.message, e.diagnostic, parent=self).exec()

    # ---------- Data ----------

    def refresh_projects(self, select_project_id: str | None = None):
        items = list_projects(self.base_projects_dir)

        self.table.setRowCount(len(items))
        for i, p in enumerate(items):
            valid = "✓" if p.valid else "✗"

            self.table.setItem(i, 0, QTableWidgetItem(valid))
            self.table.setItem(i, 1, QTableWidgetItem(p.project_id))
            self.table.setItem(i, 2, QTableWidgetItem(p.project_name))
            self.table.setItem(i, 3, QTableWidgetItem(p.created_at))
            self.table.setItem(i, 4, QTableWidgetItem(p.topic_prompt))
            self.table.setItem(i, 5, QTableWidgetItem(str(p.project_dir)))

            # subtle UX: gray out invalid rows
            if not p.valid:
                for col in range(6):
                    item = self.table.item(i, col)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                    item.setForeground(Qt.GlobalColor.gray)

        # optional: select a newly created project
        if select_project_id:
            for i, p in enumerate(items):
                if p.project_id == select_project_id:
                    self.table.selectRow(i)
                    break
