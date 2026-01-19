import sys
import os
import sqlite3

from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QLabel, QMessageBox,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QTreeWidget, QTreeWidgetItem, QWidget,
    QLineEdit, QPushButton, QHBoxLayout,
    QDialogButtonBox
)


from PySide6.QtGui import QPixmap, QColor, QBrush
from PySide6.QtCore import (
    QVariantAnimation, QParallelAnimationGroup,
    QPointF, QEasingCurve,Qt
)




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

    # フォルダが1つもない場合はルートフォルダを作成
    cur.execute("SELECT COUNT(*) FROM folders")
    count = cur.fetchone()[0]
    if count == 0:
        cur.execute(
            "INSERT INTO folders (parent_id, name) VALUES (?, ?)",
            (None, "ルート")
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

        self.on_folder_selected = on_folder_selected
        self.on_add_item = on_add_item
        self.itemSelectionChanged.connect(self.handle_selection_changed)

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

    def open_menu(self, position):
        item = self.itemAt(position)
        if not item:
            return
        menu = QMenu(self)
        folder_id = item.data(0, Qt.UserRole)
        is_top_level = self.indexOfTopLevelItem(item) != -1
        add_item_action = menu.addAction("新規アイテム追加")
        if is_top_level:
            add_folder_action = menu.addAction("新規サブフォルダを追加")
            rename_action = menu.addAction("親フォルダ名を変更")
            delete_action = None
        else:
            add_folder_action = menu.addAction("このフォルダの下にサブフォルダを追加")
            rename_action = menu.addAction("サブフォルダ名を変更")
            delete_action = menu.addAction("このサブフォルダを削除")

        action = menu.exec(self.viewport().mapToGlobal(position))

        if action == add_item_action:
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

    def add_new_folder(self, parent_item):
        parent_id = parent_item.data(0, Qt.UserRole) if parent_item else None
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

    def rename_folder(self, item):
        new_name, ok = QInputDialog.getText(self, "名前を変更", "新しいフォルダ名:")
        if not ok or not new_name:
            return
        folder_id = item.data(0, Qt.UserRole)
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE folders SET name = ? WHERE id = ?", (new_name, folder_id))
        conn.commit()
        conn.close()
        item.setText(0, new_name)

    def delete_folder(self, item):
        parent = item.parent()
        if parent is None:
            QMessageBox.information(self, "削除不可", "トップレベルフォルダは削除できません。")
            return
        folder_id = item.data(0, Qt.UserRole)
        reply = QMessageBox.question(self, "確認", "このフォルダと配下のアイテムを削除します。よろしいですか？", QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM items WHERE folder_id = ?", (folder_id,))
        cur.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
        conn.commit()
        conn.close()
        parent.removeChild(item)

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

        self.setWindowTitle("Password Manager")
        self.resize(1000, 650)
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #ffffff; }
            QLineEdit, QTextEdit { background-color: #2b2b2b; color: #ffffff; border: 1px solid #444; }
            QListWidget { background-color: #2b2b2b; color: #ffffff; border: none; }
            QTreeWidget { background-color: #2b2b2b; color: #ffffff; }
        """)

        # 左右分割
        main_splitter = QSplitter(Qt.Horizontal)

        parent_icon_path = os.path.join("png", "folder1.png")
        child_icon_path = os.path.join("png", "subfolder1.png")

        self.folder_tree = FolderTree(parent_icon_path, child_icon_path,
                                      on_folder_selected=self.on_folder_selected,
                                      on_add_item=self.on_add_item_request)
        main_splitter.addWidget(self.folder_tree)
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setSizes([260, 740])

        # 右ペイン分割
        right_splitter = QSplitter(Qt.Vertical)
        # アイテムリスト
        self.item_list = QListWidget()
        self.item_list.itemSelectionChanged.connect(self.on_item_selected)
        right_splitter.addWidget(self.item_list)

        # 詳細フォーム
        self.detail_widget = QWidget()
        self.detail_layout = QFormLayout(self.detail_widget)
        self.input_title = QLineEdit()
        self.input_username = QLineEdit()
        self.input_password = QLineEdit()
        self.input_url = QLineEdit()
        self.input_notes = QTextEdit()
        self.detail_layout.addRow("タイトル:", self.input_title)
        self.detail_layout.addRow("ユーザー名:", self.input_username)
        self.detail_layout.addRow("パスワード:", self.input_password)
        self.detail_layout.addRow("URL:", self.input_url)
        self.detail_layout.addRow("メモ:", self.input_notes)
        right_splitter.addWidget(self.detail_widget)

        right_splitter.setStretchFactor(0,1)
        right_splitter.setStretchFactor(1,0)
        right_splitter.setStretchFactor(2,1)

        main_splitter.addWidget(right_splitter)
        main_splitter.setStretchFactor(1,1)

        layout = QVBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(main_splitter)
        self.setLayout(layout)

        QTimer.singleShot(0, self.select_initial_folder)

    # 初期選択
    def select_initial_folder(self):
        root_item = self.folder_tree.topLevelItem(0)
        if root_item:
            self.folder_tree.setCurrentItem(root_item)

    # FolderTree 選択時
    def on_folder_selected(self, folder_id):
        self.current_folder_id = folder_id
        self.current_item_id = None
        self.load_items_for_folder(folder_id)

    # アイテム読み込み
    def load_items_for_folder(self, folder_id):
        self.item_list.clear()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, title FROM items WHERE folder_id = ? ORDER BY id DESC", (folder_id,))
        rows = cur.fetchall()
        conn.close()
        for item_id, title in rows:
            it = QListWidgetItem(title if title else "(タイトルなし)")
            it.setData(Qt.UserRole, item_id)
            self.item_list.addItem(it)
        if self.item_list.count() > 0:
            self.item_list.setCurrentRow(0)

    # アイテム選択時
    def on_item_selected(self):
        item = self.item_list.currentItem()
        if not item:
            return
        self.current_item_id = item.data(Qt.UserRole)
        # 詳細フォームに反映（省略可能、ここでDBから読み込む実装可）

    # アイテム追加リクエスト
    def on_add_item_request(self, folder_id):
        self.current_folder_id = folder_id
        # 新規アイテム追加処理（省略、DB挿入など）


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

        # --- ① 現在のパスワード確認（鍵ダイアログ） ---
        dlg = MasterPasswordDialog(self)
        entered = dlg.get_password()
        if entered is None:
            return
        if entered != current_pw:
            QMessageBox.warning(self, "エラー", "現在のパスワードが違います。")
            return

        # 🔓 成功演出だけ再生（ダイアログはもう閉じている）
        success = MasterPasswordDialog(self)
        success.set_message("認証成功")
        success.play_unlock_and_close()
        success.exec()

        # --- ② 新しいパスワード入力（鍵ダイアログ） ---
        dlg_new = MasterPasswordDialog(self)
        dlg_new.set_message("新しいマスターパスワードを入力してください")
        pw1 = dlg_new.get_password()
        if pw1 is None:
            return

        # --- ③ 新しいパスワード確認（鍵ダイアログ） ---
        dlg_confirm = MasterPasswordDialog(self)
        dlg_confirm.set_message("確認のため、もう一度入力してください")
        pw2 = dlg_confirm.get_password()
        if pw2 is None:
            return

        if pw1 != pw2:
            QMessageBox.warning(self, "不一致", "パスワードが一致しません。")
            return

        # --- ④ DB 更新 ---
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

    def update_password_strength(self):
        password = self.input_password.text()
        score = 0

        if len(password) >= 8:
            score += 1
        if any(c.islower() for c in password):
            score += 1
        if any(c.isupper() for c in password):
            score += 1
        if any(c.isdigit() for c in password):
            score += 1
        if any(c in "!@#$%^&*" for c in password):
            score += 1

        self.password_strength_bar.setValue(score)

        if score <= 2:
            self.password_strength_label.setText("強度：弱い")
            self.password_strength_bar.setStyleSheet(
                "QProgressBar::chunk { background-color: #d9534f; }"
            )
        elif score <= 4:
            self.password_strength_label.setText("強度：普通")
            self.password_strength_bar.setStyleSheet(
                "QProgressBar::chunk { background-color: #f0ad4e; }"
            )
        else:
            self.password_strength_label.setText("強度：強い")
            self.password_strength_bar.setStyleSheet(
                "QProgressBar::chunk { background-color: #5cb85c; }"
            )

class LockAnimationWidget(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)

        # 1Password風の横長レイアウトに合わせる
        self.setFixedSize(900, 260)
        self.setStyleSheet("background-color: #0a0f1f; border: none;")

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        # 鍵アイコンの共通サイズ
        self.icon_size = 150

        # 初期状態：閉じた鍵（サイズ統一）
        pix = QPixmap("PNG/key_close.png").scaled(
            self.icon_size, self.icon_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.lock_pix = QGraphicsPixmapItem(pix)

        # 中央に配置
        self.lock_pix.setPos(
            (self.width() - self.icon_size) / 2,
            (self.height() - self.icon_size) / 2
        )

        self.scene.addItem(self.lock_pix)

    def play_unlock(self, finished=None):
        from PySide6.QtCore import QVariantAnimation, QEasingCurve

        start_pos = self.lock_pix.pos()
        end_pos = start_pos + QPointF(0, -20)

        move = QVariantAnimation()
        move.setDuration(500)
        move.setStartValue(start_pos)
        move.setEndValue(end_pos)
        move.setEasingCurve(QEasingCurve.OutCubic)
        move.valueChanged.connect(lambda v: self.lock_pix.setPos(v))

        rotate = QVariantAnimation()
        rotate.setDuration(500)
        rotate.setStartValue(0)
        rotate.setEndValue(-15)
        rotate.valueChanged.connect(lambda v: self.lock_pix.setRotation(v))

        group = QParallelAnimationGroup()
        group.addAnimation(move)
        group.addAnimation(rotate)

        def on_finished():
            # 開いた鍵も同じサイズで読み込み
            pix = QPixmap("PNG/key_open.png").scaled(
                self.icon_size, self.icon_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.lock_pix.setPixmap(pix)

            if finished:
                finished()

        group.finished.connect(on_finished)
        group.start()
        self._anim = group

    def reset_lock(self):
        # 閉じた鍵に戻す（サイズ統一）
        pix = QPixmap("PNG/key_close.png").scaled(
            self.icon_size, self.icon_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.lock_pix.setPixmap(pix)

        # 回転リセット
        self.lock_pix.setRotation(0)

        # 中央に戻す
        self.lock_pix.setPos(
            (self.width() - self.icon_size) / 2,
            (self.height() - self.icon_size) / 2
        )

class MasterPasswordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedSize(520, 620)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(24)
        layout.setContentsMargins(40, 40, 40, 40)

        # 鍵アニメーション
        self.lock_anim = LockAnimationWidget(self)
        self.lock_anim.setFixedSize(400, 200)
        layout.addWidget(self.lock_anim, alignment=Qt.AlignCenter)

        # メッセージ
        self.msg = QLabel("マスターパスワードを入力してください")
        self.msg.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.msg)

        # パスワード入力
        self.input = QLineEdit()
        self.input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.input)

        # ボタン
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        layout.addWidget(self.buttons)

        # connect（UI 作成後に行う）
        self.input.returnPressed.connect(self.buttons.accepted.emit)
        self.buttons.accepted.connect(super().accept)
        self.buttons.rejected.connect(self.reject)

    def set_message(self, text):
        self.msg.setText(text)

    def play_unlock_and_close(self):
        self.buttons.setEnabled(False)
        self.lock_anim.reset_lock()
        self.lock_anim.play_unlock(finished=super().accept)

    def get_password(self):
        if self.exec() == QDialog.Accepted:
            return self.input.text()
        return None



# ========== エントリポイント ==========
def main():
    init_db()
    app = QApplication(sys.argv)

    if not is_master_password_set():
        if not setup_master_password():
            sys.exit(0)

    # マスターパスワード取得
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT password FROM master WHERE id = 1")
    stored_pw = cur.fetchone()[0]
    conn.close()

    # ① 入力用ダイアログ（アニメなしで普通に閉じる）
    dlg = MasterPasswordDialog()
    dlg.set_message("マスターパスワードを入力してください")

    if dlg.exec() != QDialog.Accepted:
        sys.exit(0)

    entered = dlg.input.text()
    if entered != stored_pw:
        QMessageBox.warning(None, "エラー", "マスターパスワードが違います")
        sys.exit(0)

    # ② 成功演出専用ダイアログ（入力なし）
    success = MasterPasswordDialog()
    success.set_message("認証成功")
    success.play_unlock_and_close()
    success.exec()

if __name__ == "__main__":
    main()

    
