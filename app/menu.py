"""Inline/Reply menus."""
from telegram import ReplyKeyboardMarkup, KeyboardButton

from .config import ADMIN_IDS

BTN_PREDICT = "📊 Dự đoán phiên hiện tại"
BTN_STATS = "📈 Thống kê"
BTN_HELP = "🆘 Hỗ trợ"
BTN_ADMIN = "👑 Admin"

# Admin sub menu
BTN_ADMIN_AUTO = "🚀 Chạy tự động nhóm"
BTN_ADMIN_SOURCE = "📡 Nhóm check LS"
BTN_ADMIN_BAN = "🔒 Khóa user"
BTN_ADMIN_USERS = "👥 Tổng user"
BTN_ADMIN_BROADCAST = "📢 Thông báo all"
BTN_ADMIN_SETTINGS = "⚙️ Cài đặt bot"
BTN_BACK = "⬅️ Quay lại"

# Auto-group control buttons (shown when an auto group is already configured)
BTN_AUTO_RUN = "▶️ Chạy"
BTN_AUTO_STOP = "⛔ Tắt"
BTN_AUTO_CHANGE = "🔄 Đổi nhóm"


def main_menu(user_id: int) -> ReplyKeyboardMarkup:
    """Main menu. NORMAL users never see the Admin button."""
    rows = [
        [KeyboardButton(BTN_PREDICT)],
        [KeyboardButton(BTN_STATS), KeyboardButton(BTN_HELP)],
    ]
    if user_id in ADMIN_IDS:
        rows.append([KeyboardButton(BTN_ADMIN)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def admin_menu() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(BTN_ADMIN_AUTO), KeyboardButton(BTN_ADMIN_SOURCE)],
        [KeyboardButton(BTN_ADMIN_BAN), KeyboardButton(BTN_ADMIN_USERS)],
        [KeyboardButton(BTN_ADMIN_BROADCAST), KeyboardButton(BTN_ADMIN_SETTINGS)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def auto_control_menu() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(BTN_AUTO_RUN), KeyboardButton(BTN_AUTO_STOP)],
        [KeyboardButton(BTN_AUTO_CHANGE)],
        [KeyboardButton(BTN_BACK)],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)
