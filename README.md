# Telegram Tài Xỉu Prediction Bot

Bot Python production-ready:
- **Telethon (userbot)** đọc realtime message từ bot game trong group
- Parse số phiên, xúc xắc, tổng điểm, Tài/Xỉu, Chẵn/Lẻ
- Lưu **SQLite** (`/app/data/bot.db`)
- Dự đoán phiên kế tiếp bằng **Logic (cầu 1-1, bệt, streak, đảo, momentum, rolling pattern)** + **ML ensemble (RandomForest 35% + XGBoost 35% + LogisticRegression, blend với Logic 30%)**
- Confidence cố định trong khoảng **52% – 78%**
- Tự động gửi dự đoán vào group đã cấu hình
- Auto-reconnect khi Telethon disconnect
- Menu user / admin riêng biệt
- Broadcast, khóa/mở khóa user, thống kê

## 1. Chuẩn bị

### 1.1 Lấy `API_ID` & `API_HASH`
1. Vào https://my.telegram.org
2. Đăng nhập số điện thoại Telegram → **API development tools**
3. Tạo app → copy `api_id` và `api_hash`

### 1.2 Tạo `SESSION_STRING` (chạy **local 1 lần**)
```bash
python -m venv venv && source venv/bin/activate
pip install telethon==1.36.0
python generate_session.py
```
Nhập API_ID, API_HASH, số điện thoại, mã OTP. Copy chuỗi `SESSION_STRING` xuất ra.

> ⚠️ SESSION_STRING là quyền truy cập tài khoản Telegram của bạn — **không chia sẻ**.

### 1.3 Tạo bot Telegram
1. Chat với [@BotFather](https://t.me/BotFather) → `/newbot` → lấy **BOT_TOKEN**
2. Thêm bot vào group muốn nhận dự đoán, cấp quyền gửi tin nhắn

### 1.4 Lấy `SOURCE_CHAT_ID` (group chứa bot game)
- Forward 1 message của bot game đến [@userinfobot](https://t.me/userinfobot) hoặc dùng `@RawDataBot`
- Group ID có dạng `-100xxxxxxxxxx`

### 1.5 Lấy `ADMIN_IDS`
- Mở [@userinfobot](https://t.me/userinfobot) → lấy ID của bạn
- Nhiều admin: ngăn cách bằng dấu phẩy `123,456`

---

## 2. Deploy Render.com — từng bước

### Bước 1 — Push code lên GitHub
```bash
git init
git add .
git commit -m "init telegram prediction bot"
git branch -M main
git remote add origin https://github.com/<bạn>/telegram-prediction-bot.git
git push -u origin main
```

### Bước 2 — Tạo service trên Render
1. Vào https://dashboard.render.com → **New +** → **Blueprint**
2. **Connect GitHub** → chọn repo vừa push
3. Render đọc `render.yaml` và tạo 1 **Worker** service (không cần port HTTP)
4. Click **Apply**

> Nếu không dùng Blueprint: **New + → Background Worker → Build & deploy from Docker** → trỏ vào repo. Dockerfile sẽ tự được dùng.

### Bước 3 — Cấu hình Environment Variables
Trong service vừa tạo → tab **Environment** → thêm các biến:

| Key | Giá trị |
|---|---|
| `API_ID` | (số) |
| `API_HASH` | (chuỗi) |
| `SESSION_STRING` | (chuỗi rất dài) |
| `BOT_TOKEN` | `123456:ABC...` |
| `ADMIN_IDS` | `123,456` |
| `SOURCE_CHAT_ID` | `-100xxxxxxxxxx` |
| `DB_PATH` | `/app/data/bot.db` (đã set sẵn) |
| `TZ` | `Asia/Ho_Chi_Minh` |

Bấm **Save Changes** → Render tự deploy lại.

### Bước 4 — Persistent Disk
`render.yaml` đã khai báo disk **1 GB** mount tại `/app/data` để giữ SQLite qua các lần redeploy. Nếu tạo service thủ công, vào tab **Disks** → **Add Disk**:
- Name: `bot-data`
- Mount path: `/app/data`
- Size: `1 GB`

### Bước 5 — Start Command
Đã có trong Dockerfile (`CMD ["python", "main.py"]`). **Không cần** đặt Start Command thủ công.

### Bước 6 — Kiểm tra Logs
Tab **Logs** trong Render. Bạn sẽ thấy:
```
Database initialised at /app/data/bot.db
Telegram bot started (polling).
Telethon connected as <username> (id=...)
Listening on SOURCE_CHAT_ID=-100...
```
Khi có phiên mới:
```
New session #76511 dice=[6, 3, 3] total=12 TAI CHAN
```

---

## 3. Sử dụng bot

### User thường
- `/start` → mở menu
- **📊 Dự đoán phiên hiện tại** → hiển thị dự đoán phiên kế tiếp
- **📈 Thống kê** → tổng phiên, win/loss, accuracy
- **🆘 Hỗ trợ**

### Admin
Bấm **👑 Admin** → menu admin:

- **🚀 Chạy tự động nhóm** → bot hỏi `chat_id` group → gõ `-100xxxxxxxxxx` → bot sẽ tự động gửi dự đoán vào group đó mỗi khi có phiên mới.
  - Tắt: gõ `off -100xxxxxxxxxx`
- **🔒 Khóa user** → gõ `ban <user_id>` hoặc `unban <user_id>`
- **👥 Tổng user** → thống kê user
- **📢 Thông báo all** → gõ nội dung → broadcast
- **⚙️ Cài đặt bot** → xem danh sách auto group

---

## 4. Fix lỗi thường gặp

| Lỗi | Nguyên nhân & Cách fix |
|---|---|
| `BOT_TOKEN missing` | Chưa set env `BOT_TOKEN` |
| `Missing API_ID/API_HASH/SESSION_STRING` | Userbot không chạy → set đủ 3 biến |
| `AuthKeyDuplicatedError` / phải đăng nhập lại | SESSION_STRING bị dùng nhiều nơi → tạo lại bằng `generate_session.py` |
| Bot không gửi tin vào group | Bot chưa được thêm vào group, hoặc bị tắt quyền gửi tin. Group ID phải là `-100...` |
| Không nhận message từ nguồn | Sai `SOURCE_CHAT_ID`, hoặc userbot không ở trong group đó |
| `sqlite3.OperationalError: unable to open database file` | Thiếu Persistent Disk mount vào `/app/data` |
| Worker exit code 1 ngay khi start | Xem **Logs** dòng cuối; thường do thiếu env var |
| Build fail tại `xgboost` | Đảm bảo dùng `python:3.11-slim` (đã có sẵn trong Dockerfile) |

### Restart service
Render dashboard → service → **Manual Deploy → Clear build cache & deploy** hoặc **Restart**.

### Xem logs realtime
Tab **Logs** → bật **Live**.

---

## 5. Kiến trúc

```
/app
  main.py
  app/
    config.py
    database.py
    parser.py
    logic_engine.py
    ml_model.py
    predictor.py
    formatter.py
    prediction_service.py
    telethon_listener.py
    handlers.py
    menu.py
  generate_session.py
  requirements.txt
  Dockerfile
  render.yaml
  README.md
/data        # SQLite (persistent disk)
```

## 6. Logic dự đoán

- **Logic engine**: streak/bệt, cầu 1-1, đảo cầu, momentum (10 phiên gần), rolling pattern (so khớp 3 kết quả gần nhất với lịch sử).
- **ML**: window 8 phiên → label TAI/XIU phiên kế. Ensemble RF + XGB + LR.
- **Blend cuối**: `0.7 * ML + 0.3 * Logic`, confidence clamp [0.52, 0.78].
- Khi DB < 30 phiên → 100% Logic.
- Mỗi phiên mới về sẽ **tự động chấm** dự đoán cũ → cập nhật `prediction_correct` → hiển thị win/loss.

## 7. Bảo mật
- Không hard-code secret trong code; tất cả đều qua env.
- Tài khoản userbot dùng riêng (đừng dùng tài khoản chính nếu group nhạy cảm).
- Persistent disk lưu DB cục bộ trên Render (không public).
