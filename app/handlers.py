"""python-telegram-bot handlers."""
import asyncio
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)

from .config import ADMIN_IDS, BOT_TOKEN
from .database import db
from .menu import (
    main_menu, admin_menu,
    BTN_PREDICT, BTN_STATS, BTN_HELP, BTN_ADMIN,
    BTN_ADMIN_AUTO, BTN_ADMIN_BAN, BTN_ADMIN_USERS,
    BTN_ADMIN_BROADCAST, BTN_ADMIN_SETTINGS, BTN_BACK,
)
from .prediction_service import build_next_prediction_message

log = logging.getLogger(__name__)


# Conversation state per user
PENDING = {}  # user_id -> state string


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


async def _track_and_check(update: Update) -> bool:
    u = update.effective_user
    if not u:
        return False
    await db.upsert_user(u.id, u.username or "", u.first_name or "")
    if await db.is_banned(u.id):
        try:
            await update.effective_message.reply_text("⛔ Bạn đã bị khóa khỏi bot")
        except Exception:
            pass
        return False
    return True


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _track_and_check(update):
        return
    uid = update.effective_user.id
    await update.message.reply_text(
        "👋 Chào mừng đến *Tài Xỉu Prediction Bot*\n\nDùng menu bên dưới để bắt đầu.",
        parse_mode="Markdown",
        reply_markup=main_menu(uid),
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _track_and_check(update):
        return
    await update.message.reply_text(
        "🆘 *Hỗ trợ*\n\n"
        "• Bấm 📊 để xem dự đoán phiên hiện tại\n"
        "• Bấm 📈 để xem thống kê thắng/thua\n"
        "• Admin có menu riêng để cấu hình bot",
        parse_mode="Markdown",
        reply_markup=main_menu(update.effective_user.id),
    )


async def on_predict(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # Always refresh from the source Telegram room before predicting,
    # so we react to the latest #session immediately.
    res = await build_next_prediction_message(refresh_from_source=True)
    if not res:
        await update.message.reply_text(
            "⏳ Không lấy được dữ liệu từ room nguồn. "
            "Kiểm tra SESSION_STRING / SOURCE_CHAT_USERNAME rồi thử lại."
        )
        return
    _, msg, _, _ = res
    await update.message.reply_text(msg)


async def on_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stats = await db.prediction_stats()
    total_sessions = len(await db.recent_sessions(limit=100000))
    total = stats["total"]
    wins = stats["wins"]
    losses = stats["losses"]
    acc = (wins / total * 100) if total else 0
    text = (
        "📈 *Thống kê*\n\n"
        f"🎲 Số phiên thu thập: *{total_sessions}*\n"
        f"🎯 Tổng dự đoán đã chấm: *{total}*\n"
        f"✅ Thắng: *{wins}*\n"
        f"❌ Thua: *{losses}*\n"
        f"📊 Tỉ lệ: *{acc:.1f}%*"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def on_admin_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("❌ Bạn không có quyền.")
        return
    await update.message.reply_text("👑 *Admin menu*", parse_mode="Markdown",
                                    reply_markup=admin_menu())


async def on_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    PENDING.pop(uid, None)
    await update.message.reply_text("⬅️ Quay lại menu chính", reply_markup=main_menu(uid))


async def on_admin_auto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    PENDING[uid] = "await_auto_group_id"
    await update.message.reply_text(
        "Nhập chat ID nhóm (ví dụ: -100xxxxxxxxxx)\n"
        "Gõ 'off <chat_id>' để tắt tự động cho nhóm đó."
    )


async def on_admin_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    PENDING[uid] = "await_ban"
    await update.message.reply_text(
        "Nhập: `ban <user_id>` để khóa\nhoặc `unban <user_id>` để mở khóa.",
        parse_mode="Markdown",
    )


async def on_admin_users(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    total = await db.count_users()
    active = await db.count_active_today()
    banned = await db.count_banned()
    text = (
        f"👥 Tổng user: *{total}*\n"
        f"🟢 Active hôm nay: *{active}*\n"
        f"🚫 User bị khóa: *{banned}*"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def on_admin_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    PENDING[uid] = "await_broadcast"
    await update.message.reply_text("Gửi nội dung muốn broadcast (text).")


async def on_admin_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    groups = await db.auto_groups()
    text = "⚙️ *Cài đặt bot*\n\n"
    text += f"🏠 Auto groups: {len(groups)}\n"
    for g in groups:
        text += f"• `{g}`\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _track_and_check(update):
        return
    text = (update.message.text or "").strip()
    uid = update.effective_user.id

    # Menu routing
    if text == BTN_PREDICT:
        return await on_predict(update, ctx)
    if text == BTN_STATS:
        return await on_stats(update, ctx)
    if text == BTN_HELP:
        return await cmd_help(update, ctx)
    if text == BTN_ADMIN:
        return await on_admin_entry(update, ctx)
    if text == BTN_BACK:
        return await on_back(update, ctx)
    if text == BTN_ADMIN_AUTO:
        return await on_admin_auto(update, ctx)
    if text == BTN_ADMIN_BAN:
        return await on_admin_ban(update, ctx)
    if text == BTN_ADMIN_USERS:
        return await on_admin_users(update, ctx)
    if text == BTN_ADMIN_BROADCAST:
        return await on_admin_broadcast(update, ctx)
    if text == BTN_ADMIN_SETTINGS:
        return await on_admin_settings(update, ctx)

    # Pending admin inputs
    state = PENDING.get(uid)
    if state and is_admin(uid):
        if state == "await_auto_group_id":
            PENDING.pop(uid, None)
            parts = text.split()
            if parts[0].lower() == "off" and len(parts) == 2 and parts[1].lstrip("-").isdigit():
                cid = int(parts[1])
                await db.remove_auto_group(cid)
                await update.message.reply_text(f"✅ Đã tắt auto cho `{cid}`", parse_mode="Markdown")
                return
            if not text.lstrip("-").isdigit():
                await update.message.reply_text("❌ Chat ID không hợp lệ.")
                return
            cid = int(text)
            await db.add_auto_group(cid)
            await update.message.reply_text(
                f"✅ Đã bật tự động gửi dự đoán vào nhóm `{cid}`", parse_mode="Markdown"
            )
            return

        if state == "await_ban":
            PENDING.pop(uid, None)
            parts = text.split()
            if len(parts) != 2 or parts[0].lower() not in ("ban", "unban") or not parts[1].isdigit():
                await update.message.reply_text("❌ Cú pháp sai.")
                return
            tgt = int(parts[1])
            if parts[0].lower() == "ban":
                await db.ban_user(tgt, "admin")
                await update.message.reply_text(f"🔒 Đã khóa user `{tgt}`", parse_mode="Markdown")
            else:
                await db.unban_user(tgt)
                await update.message.reply_text(f"🔓 Đã mở khóa user `{tgt}`", parse_mode="Markdown")
            return

        if state == "await_broadcast":
            PENDING.pop(uid, None)
            uids = await db.all_user_ids()
            ok, fail = 0, 0
            for u in uids:
                try:
                    await ctx.bot.send_message(u, text)
                    ok += 1
                    await asyncio.sleep(0.05)
                except Exception:
                    fail += 1
            await update.message.reply_text(f"📢 Broadcast xong. ✅ {ok} | ❌ {fail}")
            return

    # default
    await update.message.reply_text("Dùng menu bên dưới nhé.", reply_markup=main_menu(uid))


def build_application():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app
