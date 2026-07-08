# web_app.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional
from aiogram import Bot
import json
import logging
import os
from datetime import datetime, timezone, timedelta

from db import db
from migrations import run_migrations

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Kitchen Display System")

API_TOKEN = '8350331260:AAFCMbZz2WsFes2DU-FNSKYP2a35-tsZFQw'
GROUP_CHAT_ID = -1002704977137

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Все время в системе считаем по Ташкенту (UTC+5), независимо от того,
# в каком часовом поясе физически работает сервер.
TASHKENT_TZ = timezone(timedelta(hours=5))


def now_tashkent() -> datetime:
    """Текущее время в таймзоне UTC+5."""
    return datetime.now(TASHKENT_TZ)


def format_price(price) -> str:
    return f"{int(price):,}".replace(",", " ") + " сум"


def escape_markdown(text) -> str:
    if not text:
        return ""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    result = ""
    for char in str(text):
        result += ('\\' + char) if char in escape_chars else char
    return result


async def send_order_to_group(table_number: int, waiter_name: str, order_items: list, order_total: float, comment: str = "", previous_items: list = None):
    if previous_items is None:
        previous_items = []
    
    order_message = "🍽️ *НОВЫЙ ЗАКАЗ!* 🍽️\n\n"
    order_message += f"👨‍🍳 *Официант:* {escape_markdown(waiter_name)}\n"
    order_message += f"🪑 *Стол:* {table_number}\n\n"
    order_message += "📋 *Заказ:*\n"
    
    # Ранее отправленные позиции
    if previous_items:
        for item in previous_items:
            escaped_item_name = escape_markdown(item['item_name'])
            order_message += f"• {escaped_item_name} x{item['quantity']} - {format_price(item['total_price'])}\n"
        order_message += "\n✅ *ДОБАВКА*\n"
    
    # Новые позиции
    for item in order_items:
        escaped_item_name = escape_markdown(item['item_name'])
        order_message += f"• {escaped_item_name} x{item['quantity']} - {format_price(item['total_price'])}\n"

    if comment:
        order_message += f"\n💬 *Комментарий:* {escape_markdown(comment)}\n"

    order_message += f"\n💰 *Общая сумма:* {format_price(order_total)}\n"
    order_message += f"⏰ *Время:* {datetime.now().strftime('%H:%M')}"

    bot = Bot(token=API_TOKEN)
    try:
        await bot.send_message(GROUP_CHAT_ID, order_message, parse_mode='Markdown')
    finally:
        await bot.session.close()


def to_tashkent_aware(dt_value):
    """Приводит значение времени из БД к осознанному datetime в UTC+5.

    SQLite CURRENT_TIMESTAMP хранит время в UTC и возвращает его без
    таймзоны. Поэтому наивные значения из БД сначала считаем UTC, затем
    переводим в UTC+5. Если таймзона уже есть — просто конвертируем.
    """
    if not dt_value:
        return None
    if isinstance(dt_value, datetime):
        dt = dt_value
    else:
        s = str(dt_value)
        if ' ' in s and 'T' not in s:
            s = s.replace(' ', 'T')
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TASHKENT_TZ)

# Выполняем миграции при старте
try:
    run_migrations()
    logging.info("✅ Миграции выполнены успешно")
except Exception as e:
    logging.error(f"❌ Ошибка миграций: {e}")

class CartItemPayload(BaseModel):
    item_id: int
    quantity: int = Field(gt=0)


class WebAppOrderPayload(BaseModel):
    table_number: Optional[int] = None
    waiter: Optional[dict] = None
    comment: str = ""
    cart: list[CartItemPayload]


def get_webapp_menu_data() -> dict:
    categories = db.get_menu_categories()
    result_categories = []
    result_products = []

    for category_index, category_name in enumerate(categories, start=1):
        result_categories.append({
            "id": category_index,
            "name": category_name
        })

        for item in db.get_menu_items(category_name):
            result_products.append({
                "id": item["id"],
                "category_id": category_index,
                "name": item["name"],
                "price": item["price"],
                "image": item.get("image") or None,
                "prep_time": item.get("prep_time_minutes") or 10,
                "popular": False,
                "description": item.get("description") or ""
            })

    for product in result_products[:5]:
        product["popular"] = True

    return {
        "categories": result_categories,
        "products": result_products
    }


def ensure_waiter_from_webapp(waiter_data: Optional[dict]) -> dict:
    telegram_id = None
    full_name = "WebApp официант"

    if waiter_data:
        telegram_id = waiter_data.get("id")
        first_name = (waiter_data.get("first_name") or "").strip()
        last_name = (waiter_data.get("last_name") or "").strip()
        username = (waiter_data.get("username") or "").strip()
        full_name = " ".join(part for part in [first_name, last_name] if part).strip() or username or full_name

    if telegram_id is None:
        # Используем стабильный fallback ID вместо таймстампа
        telegram_id = 999999999

    db.add_waiter(int(telegram_id), full_name)
    waiter = db.get_waiter(int(telegram_id))
    if not waiter:
        raise ValueError("Не удалось создать или получить официанта")
    return waiter


async def create_order_from_webapp(payload: WebAppOrderPayload) -> dict:
    if not payload.cart:
        raise ValueError("Корзина пуста")

    table_number = payload.table_number
    if table_number is None:
        raise ValueError("Не указан номер стола")

    waiter = ensure_waiter_from_webapp(payload.waiter)
    # Проверяем любой активный заказ для стола (независимо от официанта)
    active_order = db.get_active_order_by_table(table_number)
    if not active_order:
        db.create_order(table_number, waiter["id"])
    else:
        # Обновляем официанта текущего заказа на текущего
        db.update_order_waiter(table_number, waiter["id"])

    comment = (payload.comment or "").strip()
    db.update_order_comment(table_number, comment)

    categories = db.get_menu_categories()
    menu_index = {}
    for category_name in categories:
        for item in db.get_menu_items(category_name):
            menu_index[item["id"]] = item

    for cart_item in payload.cart:
        menu_item = menu_index.get(cart_item.item_id)
        if not menu_item:
            raise ValueError(f"Позиция меню с id={cart_item.item_id} не найдена")

        db.add_order_item(
            table_number,
            menu_item["name"],
            float(menu_item["price"]),
            cart_item.quantity
        )
        db.update_item_prep_time(
            table_number,
            menu_item["name"],
            int(menu_item.get("prep_time_minutes") or 10)
        )

    new_order_items = db.get_unsent_order_items(table_number)
    if not new_order_items:
        raise ValueError("Нет новых позиций для отправки")

    db.update_order_sent_to_kitchen(table_number)

    # Получаем ВСЕ позиции стола для сообщения в телеграм
    all_items = db.get_order_items(table_number)
    # Разделяем на уже отправленные и новые
    sent_item_ids = set(item['id'] for item in new_order_items)
    previous_items = [item for item in all_items if item['id'] not in sent_item_ids]

    order_total = sum(item['total_price'] for item in all_items)

    await send_order_to_group(
        table_number=table_number,
        waiter_name=waiter.get("full_name") or "Официант",
        order_items=new_order_items,
        previous_items=previous_items,
        order_total=order_total,
        comment=comment
    )

    return {
        "table_number": table_number,
        "waiter_name": waiter.get("full_name"),
        "items_count": sum(item.quantity for item in payload.cart)
    }


# HTML шаблон прямо в коде
KITCHEN_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Кухня XonAtlas</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f7fa;
            padding: 20px;
        }
        .header {
            background: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
        }
        .header h1 {
            font-size: 24px;
            color: #1a202c;
        }
        .header .stats {
            display: flex;
            gap: 20px;
            font-size: 14px;
            color: #4a5568;
        }
        .stats span {
            background: #edf2f7;
            padding: 6px 12px;
            border-radius: 6px;
        }
        .filters {
            display: flex;
            gap: 8px;
            margin-bottom: 14px;
            flex-wrap: wrap;
        }
        .filter-btn {
            padding: 7px 14px;
            border: 1px solid #d9e2ec;
            border-radius: 8px;
            background: white;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            transition: all 0.2s;
        }
        .filter-btn.active {
            background: #4299e1;
            color: white;
            border-color: #4299e1;
        }
        .filter-btn:hover {
            border-color: #4299e1;
        }
        .orders-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
            gap: 12px;
        }
        .order-card {
            background: white;
            border-radius: 10px;
            padding: 12px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.08);
            border-left: 4px solid #48bb78;
            transition: all 0.2s;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        .order-card.warning {
            border-left-color: #ecc94b;
        }
        .order-card.overdue {
            border-left-color: #fc8181;
            animation: blinkOverdue 1.2s infinite;
        }
        @keyframes blinkOverdue {
            0% { background-color: #fff5f5; border-left-color: #fc8181; }
            50% { background-color: #fed7d7; border-left-color: #f56565; }
            100% { background-color: #fff5f5; border-left-color: #fc8181; }
        }
        .order-card.ready {
            border-left-color: #48bb78;
            background: #f0fff4;
        }
        .order-card.served {
            border-left-color: #a0aec0;
            opacity: 0.7;
        }
        .order-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 8px;
        }
        .order-table {
            font-size: 16px;
            font-weight: 700;
            color: #2d3748;
            line-height: 1.1;
        }
        .order-meta {
            font-size: 12px;
            color: #718096;
            line-height: 1.25;
        }
        .order-meta div {
            margin-bottom: 1px;
        }
.item-name {
            font-weight: 700;
            color: #1a202c;
            font-size: 20px;
            line-height: 1.3;
        }
        .item-qty {
            color: #4a5568;
            margin-left: 8px;
            font-weight: 600;
            font-size: 14px;
        }
        .item-time {
            font-size: 12px;
            padding: 3px 7px;
            border-radius: 999px;
            background: #edf2f7;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            font-weight: 600;
        }
        .item-time.on-time {
            background: #c6f6d5;
            color: #22543d;
        }
        .item-time.warning {
            background: #fefcbf;
            color: #975a16;
        }
        .item-time.overdue {
            background: #fed7d7;
            color: #9b2c2c;
        }
        .order-actions {
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
            margin-top: 2px;
        }
        .btn {
            padding: 5px 10px;
            border: none;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            line-height: 1.2;
        }
        .btn-primary {
            background: #4299e1;
            color: white;
        }
        .btn-primary:hover {
            background: #3182ce;
        }
        .btn-success {
            background: #48bb78;
            color: white;
        }
        .btn-success:hover {
            background: #38a169;
        }
        .btn-warning {
            background: #ecc94b;
            color: #744210;
        }
        .btn-warning:hover {
            background: #d69e2e;
        }
        .order-comment {
            background: #f7fafc;
            padding: 5px 8px;
            border-radius: 6px;
            font-size: 12px;
            color: #4a5568;
            border-left: 3px solid #4299e1;
            line-height: 1.25;
        }
        .progress-container {
            width: 100%;
            height: 10px;
            background: #edf2f7;
            border-radius: 10px;
            overflow: hidden;
            margin-top: 6px;
        }
        .progress-bar {
            height: 100%;
            width: 100%;
            background: #48bb78;
            transition: width 1s linear;
        }
        .progress-bar.warning {
            background: #ecc94b;
        }
        .progress-bar.overdue {
            background: #fc8181;
        }
        .empty-state {
            grid-column: 1/-1;
            text-align: center;
            padding: 40px 16px;
            color: #a0aec0;
        }
        .empty-state .icon {
            font-size: 48px;
            margin-bottom: 10px;
        }
        .empty-state .title {
            font-size: 18px;
            font-weight: 600;
            color: #4a5568;
        }
        .empty-state .subtitle {
            font-size: 13px;
            margin-top: 6px;
        }
        .card-footer {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 2px;
            flex-wrap: wrap;
            gap: 6px;
        }
        .waiter-info {
            font-size: 12px;
            color: #4a5568;
        }
        @media (max-width: 768px) {
            body {
                padding: 12px;
            }
            .orders-grid {
                grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
                gap: 10px;
            }
            .header {
                flex-direction: column;
                align-items: flex-start;
                gap: 10px;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🍳 Кухня XonAtlas</h1>
        <div class="stats" id="stats">
            <span id="totalOrders">0 заказов</span>
            <span id="pendingOrders">0 новых</span>
            <span id="cookingOrders">0 готовится</span>
            <span id="readyOrders">0 готово</span>
        </div>
    </div>

    <div class="filters">
        <button class="filter-btn active" data-filter="active">Заказы</button>
        <button class="filter-btn" data-filter="ready">Готовы</button>
    </div>

    <div class="orders-grid" id="ordersContainer">
        <div class="empty-state">
            <div class="icon">📋</div>
            <div class="title">Загрузка заказов...</div>
        </div>
    </div>

    <audio id="timeoutSound" src="/static/order.mp3" preload="auto"></audio>

    <script>
        let currentFilter = 'active';
        let ws = null;
        let activeOrders = [];
        let timeoutOrders = [];
        let seenKitchenItems = new Set();
        let hasLoadedOrdersOnce = false;
        // Разница между часами сервера и браузера (мс). Считаем её один раз при
        // каждой загрузке заказов и используем везде вместо new Date(), чтобы
        // отсчёт времени не "прыгал" на 0 из-за разных таймзон сервера и клиента.
        let serverTimeOffset = 0;

        function getServerNow() {
            return new Date(Date.now() + serverTimeOffset);
        }

        function playNewOrderSoundForItems(items) {
            const incomingKeys = items.map(item => `${item.id}-${item.item_id || item.item_name}`);
            const hasNewItems = hasLoadedOrdersOnce && incomingKeys.some(key => !seenKitchenItems.has(key));

            seenKitchenItems = new Set(incomingKeys);
            if (hasNewItems) {
                document.getElementById('timeoutSound')?.play().catch(() => {});
            }
            hasLoadedOrdersOnce = true;
        }

        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;
            
            ws = new WebSocket(wsUrl);
            
            ws.onopen = function() {
                console.log('WebSocket подключен');
            };
            
            ws.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    console.log('WebSocket обновление:', data);
                    loadOrders(currentFilter);
                } catch (e) {
                    console.error('WebSocket error:', e);
                }
            };
            
            ws.onclose = function() {
                console.log('WebSocket отключен, переподключение через 3 секунды...');
                setTimeout(connectWebSocket, 3000);
            };
        }

        function loadOrders(filter) {
            const url = !filter || filter === 'active'
                ? '/api/orders'
                : `/api/orders?status=${filter}`;
            
            fetch(url)
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        if (data.timestamp) {
                            serverTimeOffset = new Date(data.timestamp).getTime() - Date.now();
                        }
                        const items = [];
                        data.orders.forEach(order => {
                            if (order.items && order.items.length) {
                                const allItemsReady = order.items.every(i => (i.item_status || 'cooking') === 'ready');
                                order.items.forEach(item => {
                                    items.push({
                                        ...order,
                                        item_id: item.id,
                                        item: item,
                                        item_name: item.item_name,
                                        quantity: item.quantity,
                                        item_status: item.item_status || 'cooking',
                                        prep_time_minutes: item.prep_time_minutes || 10,
                                        sent_to_kitchen_at: order.sent_to_kitchen_at,
                                        allItemsReady: allItemsReady
                                    });
                                });
                            }
                        });

                        const filteredItems = items.filter(item => {
                            if (currentFilter === 'ready') {
                                return item.item_status === 'ready' && item.kitchen_status !== 'served';
                            }
                            return item.item_status !== 'ready' && item.kitchen_status !== 'served';
                        });

                        playNewOrderSoundForItems(filteredItems);
                        renderOrders(filteredItems);
                        updateStats(data.orders);
                        activeOrders = filteredItems;
                    } else {
                        console.error('Error from server:', data.error);
                    }
                })
                .catch(err => {
                    console.error('Error loading orders:', err);
                    document.getElementById('ordersContainer').innerHTML = `
                        <div class="empty-state">
                            <div class="icon">❌</div>
                            <div class="title">Ошибка загрузки</div>
                            <div class="subtitle">${err.message}</div>
                        </div>
                    `;
                });
        }

        function renderOrders(items) {
            const container = document.getElementById('ordersContainer');
            
            if (!items || items.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="icon">📋</div>
                        <div class="title">${currentFilter === 'ready' ? 'Нет готовых позиций' : 'Нет активных заказов'}</div>
                        <div class="subtitle">${currentFilter === 'ready' ? 'Готовые блюда появятся здесь' : 'Заказы появятся здесь после отправки с терминала'}</div>
                    </div>
                `;
                return;
            }

            if (currentFilter === 'ready') {
                const groupedOrders = Object.values(items.reduce((acc, item) => {
                    const key = `${item.table_number}`;
                    if (!acc[key]) {
                        acc[key] = {
                            ...item,
                            ready_items: []
                        };
                    }
                    acc[key].ready_items.push(item);
                    return acc;
                }, {}));

                let readyHtml = '';
                groupedOrders.forEach(order => {
                    readyHtml += `
                        <div class="order-card ready" data-table="${order.table_number}">
                            <div class="order-header">
                                <div>
                                    <div class="order-table">Стол ${order.table_number}</div>
                                    <div class="order-meta">
                                        <div class="waiter-info">👨‍🍳 ${order.waiter_name || 'Официант'}</div>
                                        <div>🕐 ${formatTime(order.sent_to_kitchen_at)}</div>
                                    </div>
                                </div>
                                <div class="order-meta" style="text-align: right; white-space: nowrap;">
                                    <div style="font-weight: 700; color: #2d3748;">#${order.id}</div>
                                </div>
                            </div>

                            ${order.comment ? `<div class="order-comment">💬 ${order.comment}</div>` : ''}

                            <div style="display: flex; flex-direction: column; gap: 6px;">
                                ${order.ready_items.map(readyItem => `
                                    <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; padding: 6px 8px; background: #ffffff; border-radius: 6px; border: 1px solid #c6f6d5;">
                                        <span class="item-name" style="font-size: 20px;">${readyItem.item_name}</span>
                                        <span class="item-qty">×${readyItem.quantity}</span>
                                    </div>
                                `).join('')}
                            </div>

                            <div class="card-footer">
                                <div class="order-actions">
                                    <button class="btn btn-success" onclick="updateOrderStatus(${order.table_number}, 'served')">
                                        📤 Выдать
                                    </button>
                                </div>
                                <div style="font-size: 12px; color: #48bb78; font-weight: 600;">
                                    ${order.ready_items.length} готово
                                </div>
                            </div>
                        </div>
                    `;
                });

                container.innerHTML = readyHtml;
                return;
            }

            let html = '';
            items.forEach((order) => {
                const quantity = order.quantity || 1;
                const maxPrep = (order.prep_time_minutes || 10) * quantity;
                
                let remainingTime = maxPrep;
                let timeStatus = 'on-time';
                let elapsedMinutes = 0;
                
                if (order.sent_to_kitchen_at) {
                    const start = new Date(order.sent_to_kitchen_at);
                    const now = getServerNow();
                    elapsedMinutes = (now - start) / 1000 / 60;
                    remainingTime = Math.max(0, maxPrep - elapsedMinutes);
                    
                    if (elapsedMinutes > maxPrep) {
                        timeStatus = 'overdue';
                    } else if (elapsedMinutes > maxPrep * 0.7) {
                        timeStatus = 'warning';
                    }
                }
                
                let cardClass = 'order-card';
                if (order.kitchen_status === 'served') cardClass += ' served';
                else if (timeStatus === 'overdue') cardClass += ' overdue';
                else if (timeStatus === 'warning') cardClass += ' warning';

                const progressPercent = Math.max(0, 100 - Math.min((elapsedMinutes / maxPrep) * 100, 100));

                html += `
                    <div class="${cardClass}" data-table="${order.table_number}" data-item="${order.item_name}" data-sent="${order.sent_to_kitchen_at}" data-prep="${maxPrep}" data-ready="0">
                        <div class="order-header">
                            <div>
                                <div class="order-table">Стол ${order.table_number}</div>
                                <div class="order-meta">
                                    <div class="waiter-info">👨‍🍳 ${order.waiter_name || 'Официант'}</div>
                                    <div>🕐 ${formatTime(order.sent_to_kitchen_at)}</div>
                                </div>
                            </div>
                            <div class="order-meta" style="text-align: right; white-space: nowrap;">
                                <div style="font-weight: 700; color: #2d3748;">#${order.id}</div>
                            </div>
                        </div>

                        ${order.comment ? `<div class="order-comment">💬 ${order.comment}</div>` : ''}

                        <div>
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;">
                                <span class="item-name">${order.item_name}</span>
                                <span class="item-qty">×${order.quantity}</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 3px;">
                                <span class="item-time ${timeStatus}">
                                    ⏱ ${remainingTime.toFixed(1)}/${maxPrep} мин
                                </span>
                            </div>
                            <div class="progress-container">
                                <div class="progress-bar ${timeStatus}" style="width:${progressPercent}%">
                                </div>
                            </div>
                        </div>

                        <div class="card-footer">
                            <div class="order-actions">
                                    <button class="btn btn-warning" onclick="markItemReady(${order.item_id})">
                                        ✅ Готово
                                    </button>
                            </div>
                            <div style="font-size: 12px; color: #a0aec0;">
                                #${order.id}
                            </div>
                        </div>
                    </div>
                `;
            });

            container.innerHTML = html;
        }

        function formatTime(dateStr) {
            if (!dateStr) return '—';
            const date = new Date(dateStr);
            if (isNaN(date.getTime())) return '—';
            // Всегда показываем время по Ташкенту, независимо от того,
            // в каком часовом поясе физически находится устройство официанта/кухни.
            return date.toLocaleTimeString('ru-RU', {
                hour: '2-digit',
                minute: '2-digit',
                timeZone: 'Asia/Tashkent'
            });
        }

        function updateStats(orders) {
            const uniqueTables = [...new Set(orders.map(o => o.table_number))];
            const total = uniqueTables.length;
            const pendingTables = [...new Set(orders.filter(o => o.kitchen_status === 'new').map(o => o.table_number))].length;
            const cookingTables = [...new Set(orders.filter(o => o.kitchen_status === 'cooking').map(o => o.table_number))].length;
            const readyTables = [...new Set(orders.filter(o => o.kitchen_status === 'ready').map(o => o.table_number))].length;
            
            document.getElementById('totalOrders').textContent = `${total} столов`;
            document.getElementById('pendingOrders').textContent = `${pendingTables} новых`;
            document.getElementById('cookingOrders').textContent = `${cookingTables} готовится`;
            document.getElementById('readyOrders').textContent = `${readyTables} готово`;
        }

        function markItemReady(itemId) {
            fetch(`/api/item/${itemId}/status`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({status: 'ready'})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    loadOrders(currentFilter);
                }
            })
            .catch(err => console.error('Error marking item ready:', err));
        }

        function updateOrderStatus(tableNumber, status) {
            fetch(`/api/order/${tableNumber}/status`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({status: status})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    loadOrders(currentFilter);
                }
            })
            .catch(err => console.error('Error updating order:', err));
        }

        // Фильтры
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                currentFilter = this.dataset.filter;
                loadOrders(currentFilter);
            });
        });

        // Инициализация
        connectWebSocket();
        loadOrders('active');

        // Автообновление каждые 5 секунд
        setInterval(() => {
            loadOrders(currentFilter);
        }, 5000);

        // Live таймер - обратный отсчет каждую секунду
        setInterval(() => {
            const cards = document.querySelectorAll('.order-card');
            const now = getServerNow();
            
            cards.forEach(card => {
                const sentTime = card.dataset.sent;
                const maxPrep = parseInt(card.dataset.prep) || 10;
                
                if (!sentTime || card.dataset.ready === '1') return;
                
                const start = new Date(sentTime);
                const elapsed = (now - start) / 1000 / 60;
                const remaining = Math.max(0, maxPrep - elapsed);
                
                // Определяем статус времени
                let timeStatus = 'on-time';
                if (elapsed > maxPrep) {
                    timeStatus = 'overdue';
                } else if (elapsed > maxPrep * 0.7) {
                    timeStatus = 'warning';
                }
                
                // Обновляем таймер
                const timeEl = card.querySelector('.item-time');
                if (timeEl) {
                    timeEl.textContent = `⏱ ${remaining.toFixed(1)}/${maxPrep} мин`;
                    timeEl.className = `item-time ${timeStatus}`;
                }
                
                // Обновляем прогресс-бар
                const progress = card.querySelector('.progress-bar');
                if (progress) {
                    const percent = Math.max(0, 100 - Math.min((elapsed / maxPrep) * 100, 100));
                    progress.style.width = `${percent}%`;
                    progress.className = `progress-bar ${timeStatus}`;
                }
                
                // Обновляем класс карточки для мигания (только если позиция ещё не готова/выдана)
                if (card.classList.contains('served')) return;
                
                if (elapsed > maxPrep && !card.classList.contains('overdue')) {
                    card.classList.add('overdue');
                    card.classList.remove('warning');
                } else if (elapsed <= maxPrep && elapsed > maxPrep * 0.7) {
                    card.classList.remove('overdue');
                    card.classList.add('warning');
                } else if (elapsed <= maxPrep * 0.7) {
                    card.classList.remove('overdue', 'warning');
                }
            });
        }, 1000);
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def kitchen_display():
    """Главная страница кухни"""
    return KITCHEN_HTML


@app.get("/webapp")
async def webapp_page():
    index_path = os.path.join(STATIC_DIR, "index.html")
    return FileResponse(index_path)


@app.get("/api/webapp/menu")
async def get_webapp_menu():
    try:
        return JSONResponse({
            "success": True,
            **get_webapp_menu_data()
        })
    except Exception as e:
        logging.error(f"Error getting webapp menu: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/webapp/table/{table_number}")
async def get_webapp_table_order(table_number: int):
    try:
        order_items = db.get_unsent_order_items(table_number)
        all_items = db.get_order_items(table_number)
        active_order = db.get_active_order_by_table(table_number)
        order_comment = (active_order or {}).get("comment") or ""

        # Отделяем уже отправленные позиции (для отображения)
        unsent_ids = {item["id"] for item in order_items}
        ordered_items = [item for item in all_items if item["id"] not in unsent_ids]

        return JSONResponse({
            "success": True,
            "table_number": table_number,
            "comment": order_comment,
            "items": order_items,
            "ordered_items": ordered_items
        })
    except Exception as e:
        logging.error(f"Error getting webapp table order: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/webapp/order")
async def create_webapp_order(payload: WebAppOrderPayload):
    try:
        result = await create_order_from_webapp(payload)
        return JSONResponse({
            "success": True,
            "message": f"Заказ по столу {result['table_number']} отправлен на кухню и в Telegram",
            "order": result
        })
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        logging.error(f"Error creating webapp order: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/orders")
async def get_orders(status: str = None):
    """API для получения заказов"""
    try:
        orders = db.get_kitchen_orders(status)
        
        # Добавляем расчет времени для каждого заказа
        for order in orders:
            order['time_info'] = calculate_order_time_info(order)
            order['status_class'] = get_order_status_class(order)
            # Приводим время отправки на кухню к явному UTC+5, чтобы браузер
            # клиента корректно парсил его независимо от своей таймзоны
            aware_sent = to_tashkent_aware(order.get('sent_to_kitchen_at'))
            if aware_sent:
                order['sent_to_kitchen_at'] = aware_sent.isoformat()

        return JSONResponse({
            "success": True,
            "orders": orders,
            "timestamp": now_tashkent().isoformat()
        })
    except Exception as e:
        logging.error(f"Error getting orders: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

@app.get("/api/completed")
async def get_completed_orders():
    """API для получения завершенных заказов"""
    try:
        orders = db.get_completed_orders()
        return JSONResponse({
            "success": True,
            "orders": orders
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

@app.post("/api/item/{item_id}/status")
async def update_item_status(item_id: int, request: Request):
    """Обновление статуса отдельной позиции заказа"""
    try:
        data = await request.json()
        status = data.get('status')

        if status in ['pending', 'cooking', 'ready']:
            updated = db.update_item_status_by_id(item_id, status)
            if not updated:
                return JSONResponse({"success": False, "error": "Item not found"}, status_code=404)
            return JSONResponse({"success": True})
        else:
            return JSONResponse({"success": False, "error": "Invalid status"}, status_code=400)
    except Exception as e:
        logging.error(f"Error updating item status: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.post("/api/order/{table_number}/status")
async def update_order_status(table_number: int, request: Request):
    """Обновление статуса заказа"""
    try:
        data = await request.json()
        status = data.get('status')
        
        if status in ['new', 'cooking', 'ready', 'served']:
            db.update_order_kitchen_status(table_number, status)
            return JSONResponse({"success": True})
        else:
            return JSONResponse({"success": False, "error": "Invalid status"}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass

def calculate_order_time_info(order: dict) -> dict:
    """Расчет времени для заказа - возвращает оставшееся время"""
    if not order.get('sent_to_kitchen_at'):
        return {
            'max_prep_time': 0,
            'elapsed_minutes': 0,
            'remaining_minutes': 0,
            'status': 'pending'
        }
    
    try:
        sent_time = to_tashkent_aware(order['sent_to_kitchen_at'])
        now = now_tashkent()
        elapsed_minutes = (now - sent_time).total_seconds() / 60
        
        max_prep_time = 0
        for item in order.get('items', []):
            prep_time = item.get('prep_time_minutes', 10)
            if prep_time > max_prep_time:
                max_prep_time = prep_time
        
        if max_prep_time == 0:
            max_prep_time = 10
        
        remaining_minutes = max(0, max_prep_time - elapsed_minutes)
        
        # Определяем статус
        if elapsed_minutes > max_prep_time:
            status = 'overdue'
        elif elapsed_minutes > max_prep_time * 0.7:
            status = 'warning'
        else:
            status = 'on_time'
        
        return {
            'max_prep_time': max_prep_time,
            'elapsed_minutes': round(elapsed_minutes, 1),
            'remaining_minutes': round(remaining_minutes, 1),
            'status': status,
            'sent_time': sent_time.isoformat()
        }
    except Exception as e:
        logging.error(f"Error calculating time: {e}")
        return {
            'max_prep_time': 10,
            'elapsed_minutes': 0,
            'remaining_minutes': 10,
            'status': 'pending'
        }

def get_order_status_class(order: dict) -> str:
    """Определяет CSS класс для статуса заказа"""
    time_info = order.get('time_info', {})
    status = time_info.get('status', 'on_time')
    
    kitchen_status = order.get('kitchen_status', 'new')
    if kitchen_status == 'ready':
        return 'ready'
    elif kitchen_status == 'served':
        return 'served'
    
    return status

if __name__ == "__main__":
    import uvicorn
    import socket
    
    # Проверяем свободный порт
    port = 8000
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', port))
    if result == 0:
        print(f"⚠️ Порт {port} занят, пробую порт 8001...")
        port = 8001
    
    print(f"🚀 Запуск веб-сервера на http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)