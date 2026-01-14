import sys
import os
import sqlite3

from PySide6.QtWidgets import (
    QApplication, QWidget, QSplitter, QTreeWidget, QTreeWidgetItem,
    QListWidget, QListWidgetItem, QVBoxLayout, QFormLayout, QLineEdit,
    QTextEdit, QPushButton, QHBoxLayout, QCheckBox, QMenu, QInputDialog,
    QMessageBox
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt


DB_PATH = "password_manager.db"


# ========== DB ヘルパ ==========

def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # フォルダテーブル
    cur.execute("""
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER,
            name TEXT NOT NULL
        )
    """)

    # アイテムテーブル
    cur.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_id INTEGER NOT NULL,
            title TEXT,
            username TEXT,
            password TEXT,
            url TEXT,
            notes TEXT,
            FOREIGN KEY(folder_id) REFERENCES folders(id) ON DELETE CASCADE
        )
    """)

    # マスターパスワードテーブル
    cur.execute("""
        CREATE TABLE IF NOT EXISTS master (
            id INTEGER PRIMARY KEY,
            password TEXT NOT NULL
        )
    """)

    # フォルダが1つもない場合はデフォルトフォルダを作成
    cur.execute("SELECT COUNT(*) FROM folders")
    count = cur.fetchone()[0]
    if count == 0:
        cur.execute(
            "INSERT INTO folders (parent_id, name) VALUES (?, ?)",
            (None, "デフォルト")
        )

    conn.commit()
    conn.close()


def is_master_password_set():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM master")
    count = cur.fetchone()[0]
    conn.close()
    return count > 0


def setup_master_password():
    """
    初回起動時用：
    master テーブルが空ならここでマスターパスワードを新規設定する。
    ユーザーに2回入力させ、一致したら INSERT。
    """
    while True:
        pw1, ok1 = QInputDialog.getText(
            None,
            "マスターパスワード設定",
            "マスターパスワードを入力してください:",
            QLineEdit.Password
        )
        if not ok1:
            return False

        pw2, ok2 = QInputDialog.getText(
            None,
            "マスターパスワード設定",
            "確認のため、もう一度入力してください:",
            QLineEdit.Password
        )
        if not ok2:
            return False

        if pw1 != pw2:
            QMessageBox.warning(
                None,
                "不一致",
                "パスワードが一致しません。もう一度入力してください。"
            )
            continue

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM master")  # 念のためクリア
        cur.execute(
            "INSERT INTO master (id, password) VALUES (?, ?)",
            (1, pw1)
        )
        conn.commit()
        conn.close()

        QMessageBox.information(
            None,
            "設定完了",
            "マスターパスワードを設定しました。"
        )
        return True


def verify_master_password(parent_widget=None):
    """
    通常起動時用：
    master テーブルに保存されているパスワードと照合する。
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT password FROM master WHERE id = 1")
    row = cur.fetchone()
    conn.close()

    if not row:
        # 何らかの理由で master が空なら、認証スキップ（安全側に振るなら False にしてもよい）
        return True

    stored = row[0]

    for _ in range(3):
        entered, ok = QInputDialog.getText(
            parent_widget,
            "マスターパスワード",
            "マスターパスワードを入力してください:",
            QLineEdit.Password
        )
        if not ok:
            return False
        if entered == stored:
            return True

        QMessageBox.warning(
            parent_widget,
            "エラー",
            "マスターパスワードが違います。"
        )

    return False


# ========== FolderTree ==========

class FolderTree(QTreeWidget):
    def __init__(self, parent_icon_path, child_icon_path,
                 on_folder_selected=None, on_add_item=None):
        super().__init__()

        self.setHeaderHidden(True)
        self.setIndentation(24)

        self.parent_icon = QIcon(parent_icon_path) if os.path.exists(parent_icon_path) else QIcon()
        self.child_icon = QIcon(child_icon_path) if os.path.exists(child_icon_path) else QIcon()

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.open_menu)

        # MainWindow から受け取るコールバック
        self.on_folder_selected = on_folder_selected     # folder_id を渡す
        self.on_add_item = on_add_item                   # folder_id を渡す（新規アイテム用）

        self.itemSelectionChanged.connect(self.handle_selection_changed)

        # DB からフォルダを読み込む
        self.load_folders_from_db()

    def load_folders_from_db(self):
        self.clear()

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, parent_id, name FROM folders")
        rows = cur.fetchall()
        conn.close()

        items = {}

        for folder_id, parent_id, name in rows:
            item = QTreeWidgetItem([name])
            item.setData(0, Qt.UserRole, folder_id)

            if parent_id is None:
                item.setIcon(0, self.parent_icon)
                self.addTopLevelItem(item)
            else:
                parent_item = items.get(parent_id)
                if parent_item:
                    item.setIcon(0, self.child_icon)
                    parent_item.addChild(item)

            items[folder_id] = item

        # ここでは on_folder_selected は呼ばない（MainWindow 側で初期選択を行う）

    # ---------- 右クリックメニュー ----------

    def open_menu(self, position):
        item = self.itemAt(position)
        if not item:
            return

        menu = QMenu(self)

        folder_id = item.data(0, Qt.UserRole)
        is_top_level = self.indexOfTopLevelItem(item) != -1

        # 共通メニュー
        add_item_action = menu.addAction("新規アイテム追加")

        if is_top_level:
            add_folder_action = menu.addAction("新規サブフォルダを追加")
            rename_action = menu.addAction("親フォルダ名を変更")
            delete_action = None  # トップレベルは削除しない仕様
        else:
            add_folder_action = menu.addAction("このフォルダの下にサブフォルダを追加")
            rename_action = menu.addAction("サブフォルダ名を変更")
            delete_action = menu.addAction("このサブフォルダを削除")

        action = menu.exec(self.viewport().mapToGlobal(position))

        if action == add_item_action:
            # フォルダを選択状態にしてから MainWindow に通知
            self.setCurrentItem(item)
            if self.on_folder_selected:
                self.on_folder_selected(folder_id)
            if self.on_add_item:
                self.on_add_item(folder_id)

        elif action == add_folder_action:
            self.add_new_folder(item)

        elif action == rename_action:
            self.rename_folder(item)

        elif delete_action is not None and action == delete_action:
            self.delete_folder(item)

    # ---------- フォルダ追加 ----------

    def add_new_folder(self, parent_item):
        if parent_item is None:
            parent_item = self.invisibleRootItem()

        parent_id = parent_item.data(0, Qt.UserRole)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO folders (parent_id, name) VALUES (?, ?)",
            (parent_id, "新規サブフォルダ")
        )
        new_id = cur.lastrowid
        conn.commit()
        conn.close()

        new_item = QTreeWidgetItem(["新規サブフォルダ"])
        new_item.setData(0, Qt.UserRole, new_id)
        new_item.setIcon(0, self.child_icon)

        parent_item.addChild(new_item)
        parent_item.setExpanded(True)

    # ---------- フォルダ名変更 ----------

    def rename_folder(self, item):
        new_name, ok = QInputDialog.getText(self, "名前を変更", "新しいフォルダ名:")
        if not ok or not new_name:
            return

        folder_id = item.data(0, Qt.UserRole)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE folders SET name = ? WHERE id = ?",
            (new_name, folder_id)
        )
        conn.commit()
        conn.close()

        item.setText(0, new_name)

    # ---------- フォルダ削除 ----------

    def delete_folder(self, item):
        parent = item.parent()
        if parent is None:
            # トップレベルフォルダは削除しない仕様
            QMessageBox.information(self, "削除不可", "トップレベルフォルダは削除できません。")
            return

        folder_id = item.data(0, Qt.UserRole)

        reply = QMessageBox.question(
            self, "確認",
            "このフォルダと配下のアイテムを削除します。よろしいですか？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM items WHERE folder_id = ?", (folder_id,))
        cur.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
        conn.commit()
        conn.close()

        parent.removeChild(item)

    # ---------- 選択変更時のハンドラ ----------

    def handle_selection_changed(self):
        item = self.currentItem()
        if item and self.on_folder_selected:
            folder_id = item.data(0, Qt.UserRole)
            self.on_folder_selected(folder_id)


# ========== MainWindow ==========

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.current_folder_id = None
        self.current_item_id = None

        # ---------- スタイル ----------
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QTreeWidget {
                background-color: #252526;
                border-right: 1px solid #333333;
            }
            QListWidget {
                background-color: #1e1e1e;
                border-bottom: 1px solid #333333;
            }
            QLabel {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QLineEdit, QTextEdit {
                background-color: #1e1e1e;
                border: 1px solid #3c3c3c;
            }
            QPushButton {
                background-color: #0e639c;
                border: none;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)

        self.setWindowTitle("Password Manager")
        self.resize(1000, 650)

        main_splitter = QSplitter(Qt.Horizontal)

        # ---------- 左ペイン：フォルダツリー ----------
        parent_icon_path = os.path.join("png", "folder1.png")
        child_icon_path = os.path.join("png", "subfolder1.png")

        self.folder_tree = FolderTree(
            parent_icon_path,
            child_icon_path,
            on_folder_selected=self.on_folder_selected,
            on_add_item=self.on_add_item_request
        )
        main_splitter.addWidget(self.folder_tree)
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setSizes([260, 740])

        # ---------- 右ペイン（上下分割） ----------
        right_splitter = QSplitter(Qt.Vertical)

        # ===== 右上：アイテム一覧 =====
        item_list_container = QWidget()
        item_list_layout = QVBoxLayout(item_list_container)

        self.item_list = QListWidget()  # ← ここが重要（先に作る）
        self.item_list.itemSelectionChanged.connect(self.on_item_selected)

        item_list_layout.addWidget(self.item_list)

        right_splitter.addWidget(item_list_container)

        # ===== 右下：詳細フォーム =====
        self.detail_widget = QWidget()
        self.detail_layout = QFormLayout(self.detail_widget)

        self.input_title = QLineEdit()
        self.input_username = QLineEdit()

        # パスワード欄
        password_row = QWidget()
        password_layout = QHBoxLayout(password_row)
        password_layout.setContentsMargins(0, 0, 0, 0)

        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.Password)

        self.show_password_checkbox = QCheckBox("表示")
        self.show_password_checkbox.toggled.connect(self.toggle_password_visibility)

        self.generate_password_button = QPushButton("生成")
        self.generate_password_button.clicked.connect(self.generate_password)

        password_layout.addWidget(self.input_password)
        password_layout.addWidget(self.show_password_checkbox)
        password_layout.addWidget(self.generate_password_button)

        self.input_url = QLineEdit()
        self.input_notes = QTextEdit()

        self.save_button = QPushButton("保存")
        self.save_button.clicked.connect(self.save_item)

        self.detail_layout.addRow("タイトル", self.input_title)
        self.detail_layout.addRow("ユーザー名", self.input_username)
        self.detail_layout.addRow("パスワード", password_row)
        self.detail_layout.addRow("URL", self.input_url)
        self.detail_layout.addRow("メモ", self.input_notes)
        self.detail_layout.addRow(self.save_button)

        right_splitter.addWidget(self.detail_widget)
        right_splitter.setStretchFactor(0, 1)

        main_splitter.addWidget(right_splitter)
        main_splitter.setStretchFactor(1, 1)

        # ---------- 全体レイアウト ----------
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(main_splitter)
        self.setLayout(layout)

        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.select_initial_folder)

        # 表示チェックの初期状態に応じて表示モードを反映
        self.toggle_password_visibility(self.show_password_checkbox.checkState())

    def select_initial_folder(self):
        first = self.folder_tree.topLevelItem(0)
        if first:
            self.folder_tree.setCurrentItem(first)
            folder_id = first.data(0, Qt.UserRole)
            self.on_folder_selected(folder_id)


    # ========== フォルダ選択時 ==========

    def on_folder_selected(self, folder_id):
        self.current_folder_id = folder_id
        self.current_item_id = None
        self.clear_detail_form()
        self.load_items_for_folder(folder_id)

    def load_items_for_folder(self, folder_id):
        self.item_list.clear()

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, title FROM items WHERE folder_id = ? ORDER BY id DESC",
            (folder_id,)
        )
        rows = cur.fetchall()
        conn.close()

        for item_id, title in rows:
            title_display = title if title else "(タイトルなし)"
            item_widget = QListWidgetItem(title_display)
            item_widget.setData(Qt.UserRole, item_id)
            self.item_list.addItem(item_widget)

        if self.item_list.count() > 0:
            self.item_list.setCurrentRow(0)

    # ========== アイテム選択時 ==========

    def on_item_selected(self):
        item_widget = self.item_list.currentItem()
        if not item_widget:
            self.current_item_id = None
            self.clear_detail_form()
            return

        item_id = item_widget.data(Qt.UserRole)
        self.current_item_id = item_id

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT title, username, password, url, notes
            FROM items WHERE id = ?
        """, (item_id,))
        row = cur.fetchone()
        conn.close()

        if row:
            title, username, password, url, notes = row
            self.input_title.setText(title or "")
            self.input_username.setText(username or "")
            self.input_password.setText(password or "")
            self.input_url.setText(url or "")
            self.input_notes.setPlainText(notes or "")


    # ========== 新規アイテム追加（右上ボタン） ==========

    def add_new_item_button_clicked(self):
        if self.current_folder_id is None:
            QMessageBox.information(self, "フォルダ未選択", "先にフォルダを選択してください。")
            return
        self.create_item_in_folder(self.current_folder_id)

    # ========== 新規アイテム追加（フォルダツリー右クリック） ==========

    def on_add_item_request(self, folder_id):
        self.current_folder_id = folder_id
        self.create_item_in_folder(folder_id)

    def create_item_in_folder(self, folder_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO items (folder_id, title, username, password, url, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (folder_id, "新規アイテム", "", "", "", ""))
        new_id = cur.lastrowid
        conn.commit()
        conn.close()

        self.load_items_for_folder(folder_id)

        for i in range(self.item_list.count()):
            it = self.item_list.item(i)
            if it.data(Qt.UserRole) == new_id:
                self.item_list.setCurrentItem(it)
                break

    # ========== 保存ボタン ==========

    def save_item(self):
        if self.current_item_id is None:
            QMessageBox.information(self, "アイテム未選択", "保存するアイテムが選択されていません。")
            return

        title = self.input_title.text()
        username = self.input_username.text()
        password = self.input_password.text()
        url = self.input_url.text()
        notes = self.input_notes.toPlainText()

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE items
            SET title = ?, username = ?, password = ?, url = ?, notes = ?
            WHERE id = ?
        """, (title, username, password, url, notes, self.current_item_id))
        conn.commit()
        conn.close()

        current = self.item_list.currentItem()
        if current:
            current.setText(title if title else "(タイトルなし)")

        QMessageBox.information(self, "保存", "アイテムを保存しました。")

    # ========== パスワード表示切替 ==========

    def toggle_password_visibility(self, visible: bool):
        self.input_password.setEchoMode(
            QLineEdit.Normal if visible else QLineEdit.Password
        )

    # ========== パスワード自動生成 ==========

    def generate_password(self):
        import secrets, string
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(secrets.choice(chars) for _ in range(16))
        self.input_password.setText(password)

    # ========== 設定メニュー（マスターパスワード変更） ==========

    def open_settings_menu(self):
        menu = QMenu(self)
        change_pw_action = menu.addAction("マスターパスワード変更")
        action = menu.exec(self.settings_button.mapToGlobal(self.settings_button.rect().bottomLeft()))

        if action == change_pw_action:
            self.change_master_password()

    def change_master_password(self):
        # 現在のパスワード取得
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT password FROM master WHERE id = 1")
        row = cur.fetchone()
        conn.close()

        if not row:
            QMessageBox.warning(self, "エラー", "マスターパスワードが未設定です。")
            return

        current_pw = row[0]

        entered, ok = QInputDialog.getText(
            self,
            "認証",
            "現在のマスターパスワード:",
            QLineEdit.Password
        )
        if not ok:
            return
        if entered != current_pw:
            QMessageBox.warning(self, "エラー", "現在のパスワードが違います。")
            return

        pw1, ok1 = QInputDialog.getText(
            self,
            "新しいパスワード",
            "新しいマスターパスワード:",
            QLineEdit.Password
        )
        if not ok1:
            return

        pw2, ok2 = QInputDialog.getText(
            self,
            "新しいパスワード",
            "確認のため、もう一度入力してください:",
            QLineEdit.Password
        )
        if not ok2:
            return

        if pw1 != pw2:
            QMessageBox.warning(self, "不一致", "パスワードが一致しません。")
            return

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE master SET password = ? WHERE id = 1", (pw1,))
        conn.commit()
        conn.close()

        QMessageBox.information(self, "完了", "マスターパスワードを変更しました。")

    # ========== フォームクリア ==========

    def clear_detail_form(self):
        self.input_title.clear()
        self.input_username.clear()
        self.input_password.clear()
        self.input_url.clear()
        self.input_notes.clear()


# ========== エントリポイント ==========

def main():
    init_db()

    app = QApplication(sys.argv)

    # 初回起動（master 未設定）の場合は新規設定
    if not is_master_password_set():
        if not setup_master_password():
            # 設定をキャンセルした場合は終了
            sys.exit(0)

    # 通常認証
    if not verify_master_password():
        QMessageBox.critical(None, "認証失敗", "マスターパスワードが一致しません。終了します。")
        sys.exit(1)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
