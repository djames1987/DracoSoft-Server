import asyncio
import sys
from datetime import datetime

import qasync
from PyQt6.QtCore import QTimer, pyqtSlot, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QTableWidget,
                             QTableWidgetItem, QStatusBar, QHeaderView, QMessageBox,
                             QTabWidget, QTextEdit, QLineEdit)

from DracoSoft_Server.core.baseModule import BaseModule, ModuleInfo, ModuleState


class ServerMonitorThread(QThread):
    """Background thread for monitoring server status"""
    status_updated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, server_module, interval=1000):
        super().__init__()
        self.server_module = server_module
        self.running = True
        self.interval = interval  # Interval in milliseconds

    def set_interval(self, interval):
        """Set the monitoring interval"""
        self.interval = interval

    def run(self):
        """Run the monitoring loop"""
        while self.running:
            try:
                # Get server status
                status = {
                    'modules': self.server_module.server.module_manager.get_all_modules_status(),
                    'timestamp': datetime.now().isoformat()
                }
                self.status_updated.emit(status)
            except Exception as e:
                self.error_occurred.emit(str(e))

            # Sleep for interval duration (converting ms to seconds)
            self.msleep(self.interval)


class ModuleTableWidget(QTableWidget):
    """Custom table widget for displaying module status"""

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        """Setup the table UI"""
        headers = ['Module', 'Status', 'Version', 'Actions']
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)


class ServerGUI(QMainWindow):
    def __init__(self, server_module):
        super().__init__()
        self.server_module = server_module
        self.monitor_thread = ServerMonitorThread(server_module)
        self.setup_ui()
        self.setup_monitoring()

        # Use QTimer for periodic updates instead of direct event loop
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.refresh_status)
        self.update_timer.start(1000)  # Update every second

    def setup_ui(self):
        """Setup the main window UI"""
        self.setWindowTitle("DracoSoft Server Manager")
        self.setMinimumSize(800, 600)

        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Create tab widget
        tab_widget = QTabWidget()
        layout.addWidget(tab_widget)

        # Modules tab
        modules_tab = QWidget()
        modules_layout = QVBoxLayout(modules_tab)

        # Initialize and setup module table
        self.module_table = QTableWidget()
        headers = ['Module', 'Status', 'Version', 'Actions']
        self.module_table.setColumnCount(len(headers))
        self.module_table.setHorizontalHeaderLabels(headers)

        # Set specific column widths
        self.module_table.setColumnWidth(0, 200)  # Module name
        self.module_table.setColumnWidth(1, 100)  # Status
        self.module_table.setColumnWidth(2, 100)  # Version
        self.module_table.setColumnWidth(3, 250)  # Actions

        # Set column resize modes
        self.module_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.module_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.module_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.module_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)

        # Set row height
        self.module_table.verticalHeader().setDefaultSectionSize(50)

        # Hide vertical header
        self.module_table.verticalHeader().setVisible(False)

        # Add table to layout
        modules_layout.addWidget(self.module_table)

        # Control buttons
        button_layout = QHBoxLayout()

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("refreshButton")
        self.refresh_button.clicked.connect(self.refresh_status)
        button_layout.addWidget(self.refresh_button)

        self.shutdown_button = QPushButton("Shutdown Server")
        self.shutdown_button.setObjectName("shutdownButton")
        self.shutdown_button.clicked.connect(self.confirm_shutdown)
        button_layout.addWidget(self.shutdown_button)

        modules_layout.addLayout(button_layout)

        # Add modules tab
        tab_widget.addTab(modules_tab, "Modules")

        # Logs tab
        logs_tab = QWidget()
        logs_layout = QVBoxLayout(logs_tab)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        logs_layout.addWidget(self.log_view)

        # Log filter
        filter_layout = QHBoxLayout()
        self.log_filter = QLineEdit()
        self.log_filter.setPlaceholderText("Filter logs...")
        self.log_filter.textChanged.connect(self.filter_logs)
        filter_layout.addWidget(self.log_filter)

        clear_logs_button = QPushButton("Clear")
        clear_logs_button.clicked.connect(self.log_view.clear)
        filter_layout.addWidget(clear_logs_button)

        logs_layout.addLayout(filter_layout)

        # Add logs tab
        tab_widget.addTab(logs_tab, "Logs")

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Apply modern styling
        self.apply_style()

    def _create_action_buttons(self, module_name: str, module_state: str) -> QWidget:
        """Create action buttons for a module row"""
        actions_widget = QWidget()
        actions_layout = QHBoxLayout(actions_widget)
        actions_layout.setContentsMargins(4, 4, 4, 4)
        actions_layout.setSpacing(8)

        if module_state == "ENABLED":
            disable_btn = QPushButton("Disable")
            disable_btn.setFixedWidth(90)
            disable_btn.clicked.connect(lambda: self.disable_module(module_name))
            actions_layout.addWidget(disable_btn)
        else:
            enable_btn = QPushButton("Enable")
            enable_btn.setFixedWidth(90)
            enable_btn.clicked.connect(lambda: self.enable_module(module_name))
            actions_layout.addWidget(enable_btn)

        restart_btn = QPushButton("Restart")
        restart_btn.setFixedWidth(90)
        restart_btn.clicked.connect(lambda: self.restart_module(module_name))
        actions_layout.addWidget(restart_btn)

        # Add stretch to center-align the buttons
        actions_layout.addStretch()

        return actions_widget

    def apply_style(self):
        """Apply modern styling to the GUI with better readability"""
        style = """
        QMainWindow {
            background-color: #2b2b2b;
            color: #ffffff;
        }
        QTableWidget {
            background-color: #333333;
            color: #ffffff;
            gridline-color: #555555;
            border: none;
            font-size: 10pt;
        }
        QTableWidget::item {
            padding: 5px;
        }
        QTableWidget::item:selected {
            background-color: #0066cc;
        }
        QHeaderView::section {
            background-color: #444444;
            color: #ffffff;
            padding: 8px;
            border: none;
            font-size: 10pt;
            font-weight: bold;
        }
        QPushButton {
            background-color: #0066cc;
            color: #ffffff;
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            font-size: 10pt;
            font-weight: bold;
            min-width: 90px;
            max-width: 90px;
        }
        QPushButton:hover {
            background-color: #0077ee;
        }
        QPushButton:pressed {
            background-color: #0055bb;
        }
        QPushButton:disabled {
            background-color: #555555;
            color: #888888;
        }
        QPushButton[danger=true] {
            background-color: #cc3333;
        }
        QPushButton[danger=true]:hover {
            background-color: #ee3939;
        }
        QTabWidget::pane {
            border: none;
            background-color: #333333;
        }
        QTabBar::tab {
            background-color: #444444;
            color: #ffffff;
            padding: 8px 15px;
            border: none;
            margin-right: 2px;
            font-size: 10pt;
        }
        QTabBar::tab:selected {
            background-color: #0066cc;
            font-weight: bold;
        }
        QTextEdit {
            background-color: #333333;
            color: #ffffff;
            border: none;
            font-family: Consolas, monospace;
            font-size: 10pt;
            padding: 5px;
        }
        QLineEdit {
            background-color: #444444;
            color: #ffffff;
            border: none;
            padding: 8px;
            border-radius: 4px;
            font-size: 10pt;
        }
        QStatusBar {
            background-color: #333333;
            color: #ffffff;
            font-size: 9pt;
        }
        QLabel {
            color: #ffffff;
            font-size: 10pt;
        }
        QPushButton#refreshButton {
            background-color: #2d8659;
        }
        QPushButton#refreshButton:hover {
            background-color: #35a066;
        }
        QPushButton#shutdownButton {
            background-color: #cc3333;
        }
        QPushButton#shutdownButton:hover {
            background-color: #ee3939;
        }
        """
        self.setStyleSheet(style)

        # Set default font for the entire application
        font = QFont("Segoe UI", 10)
        QApplication.setFont(font)

    def setup_monitoring(self):
        """Setup the monitoring thread"""
        self.monitor_thread.status_updated.connect(self.update_status)
        self.monitor_thread.error_occurred.connect(self.show_error)
        self.monitor_thread.start()

    @pyqtSlot(dict)
    def update_status(self, status):
        """Update the UI with new status information"""
        modules = status['modules']
        self.module_table.setRowCount(len(modules))

        for row, (name, info) in enumerate(modules.items()):
            # Module name
            name_item = QTableWidgetItem(name)
            self.module_table.setItem(row, 0, name_item)

            # Status with color
            status_item = QTableWidgetItem(info['state'])
            if info['state'] == 'ENABLED':
                status_item.setForeground(QColor('#00ff00'))
            elif info['state'] == 'DISABLED':
                status_item.setForeground(QColor('#ff0000'))
            self.module_table.setItem(row, 1, status_item)

            # Version
            version_item = QTableWidgetItem(info['version'])
            self.module_table.setItem(row, 2, version_item)

            # Action buttons
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)

            if info['state'] == 'ENABLED' or info['state'] == 'enabled':
                disable_btn = QPushButton("Disable")
                disable_btn.clicked.connect(lambda x, n=name: self.disable_module(n))
                actions_layout.addWidget(disable_btn)
            else:
                enable_btn = QPushButton("Enable")
                enable_btn.clicked.connect(lambda x, n=name: self.enable_module(n))
                actions_layout.addWidget(enable_btn)

            restart_btn = QPushButton("Restart")
            restart_btn.clicked.connect(lambda x, n=name: self.restart_module(n))
            actions_layout.addWidget(restart_btn)

            self.module_table.setCellWidget(row, 3, actions_widget)

        # Update status bar
        self.status_bar.showMessage(f"Last updated: {status['timestamp']}")

    def show_error(self, error_msg):
        """Show error message"""
        QMessageBox.critical(self, "Error", error_msg)

    def confirm_shutdown(self):
        """Confirm server shutdown"""
        reply = QMessageBox.question(
            self,
            "Confirm Shutdown",
            "Are you sure you want to shutdown the server?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            asyncio.create_task(self.server_module.server.shutdown())

    @pyqtSlot()
    def refresh_status(self):
        """Manually refresh status"""
        try:
            status = {
                'modules': self.server_module.server.module_manager.get_all_modules_status(),
                'timestamp': datetime.now().isoformat()
            }
            self.update_status(status)
        except Exception as e:
            self.show_error(str(e))

    def enable_module(self, module_name):
        """Enable a module"""
        try:
            asyncio.create_task(
                self.server_module.server.module_manager.enable_module(module_name)
            )
            self.refresh_status()
        except Exception as e:
            self.show_error(f"Failed to enable {module_name}: {str(e)}")

    def disable_module(self, module_name):
        """Disable a module"""
        try:
            asyncio.create_task(
                self.server_module.server.module_manager.disable_module(module_name)
            )
            self.refresh_status()
        except Exception as e:
            self.show_error(f"Failed to disable {module_name}: {str(e)}")

    def restart_module(self, module_name):
        """Restart a module"""
        try:
            asyncio.create_task(
                self.server_module.server.module_manager.reload_module(module_name)
            )
            self.refresh_status()
        except Exception as e:
            self.show_error(f"Failed to restart {module_name}: {str(e)}")

    def filter_logs(self):
        """Filter log entries based on search text"""
        filter_text = self.log_filter.text().lower()
        log_text = self.log_view.toPlainText()

        if not filter_text:
            self.log_view.setPlainText(log_text)
            return

        filtered_lines = [
            line for line in log_text.split('\n')
            if filter_text in line.lower()
        ]
        self.log_view.setPlainText('\n'.join(filtered_lines))

    def closeEvent(self, event):
        """Handle window close event"""
        self.monitor_thread.running = False
        self.monitor_thread.wait()
        self.update_timer.stop()
        event.accept()


class ServerGUIModule(BaseModule):
    """Module for the server management GUI"""
    def __init__(self, server):
        super().__init__(server)
        self.module_info = ModuleInfo(
            name="ServerGUI",
            version="1.0.0",
            description="GUI for server management",
            author="DracoSoft",
            dependencies=[]
        )
        self.app = None
        self.gui = None
        self._qt_loop = None

    async def load(self) -> bool:
        """Load the GUI module"""
        try:
            # Create QApplication instance
            self.app = QApplication.instance()
            if not self.app:
                self.app = QApplication(sys.argv)

            # Create qasync loop
            self._qt_loop = qasync.QEventLoop(self.app)
            asyncio.set_event_loop(self._qt_loop)

            self.state = ModuleState.LOADED
            self.logger.info("Server GUI module loaded")
            return True

        except Exception as e:
            self.logger.error(f"Failed to load server GUI module: {e}")
            self.state = ModuleState.ERROR
            return False

    def _update_config(self, user_config: dict):
        """Deep update configuration with user settings"""

        def update_dict(d, u):
            for k, v in u.items():
                if isinstance(v, dict) and k in d:
                    d[k] = update_dict(d[k], v)
                else:
                    d[k] = v
            return d

        update_dict(self.config, user_config)

    async def enable(self) -> bool:
        """Enable the GUI module"""
        try:
            # Create and show GUI
            self.gui = ServerGUI(self)
            self.gui.show()

            # Run the Qt event loop in the background
            asyncio.create_task(self._run_qt_loop())

            self.state = ModuleState.ENABLED
            self.logger.info("Server GUI module enabled")
            return True

        except Exception as e:
            self.logger.error(f"Failed to enable server GUI module: {e}")
            return False

    async def _run_qt_loop(self):
        """Run the Qt event loop"""
        try:
            # Run Qt event loop until window is closed
            while self.gui and self.gui.isVisible():
                await asyncio.sleep(0.1)  # Give control back to asyncio periodically
                self.app.processEvents()  # Process Qt events
        except Exception as e:
            self.logger.error(f"Qt event loop error: {e}")

    async def disable(self) -> bool:
        """Disable the GUI module"""
        try:
            if self.gui:
                # Stop the monitoring thread
                self.gui.monitor_thread.running = False
                self.gui.monitor_thread.wait()

                # Close the GUI
                self.gui.close()
                self.gui.deleteLater()
                self.gui = None

            self.state = ModuleState.DISABLED
            self.logger.info("Server GUI module disabled")
            return True

        except Exception as e:
            self.logger.error(f"Failed to disable server GUI module: {e}")
            return False

    async def unload(self) -> bool:
        """Unload the GUI module"""
        try:
            if self.is_enabled:
                await self.disable()

            if self.app:
                self.app.quit()
                self.app = None

            self.state = ModuleState.UNLOADED
            self.logger.info("Server GUI module unloaded")
            return True

        except Exception as e:
            self.logger.error(f"Failed to unload server GUI module: {e}")
            return False