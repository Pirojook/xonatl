import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

class Database:
    def __init__(self, db_name: str = 'restaurant.db'):
        self.db_name = db_name
        self.init_database()

    def init_database(self):
        """Инициализация базы данных и создание таблиц"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            
            # Таблица официантов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS waiters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    full_name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица столов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tables (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_number INTEGER UNIQUE NOT NULL,
                    capacity INTEGER DEFAULT 4,
                    is_available BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица заказов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_number INTEGER NOT NULL,
                    waiter_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'active', -- active, completed, cancelled
                    total_amount REAL DEFAULT 0,
                    comment TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (waiter_id) REFERENCES waiters (id)
                )
            ''')
            
            # Таблица позиций заказа
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_number INTEGER NOT NULL,
                    item_name TEXT NOT NULL,
                    item_price REAL NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    total_price REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS menu_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Таблица меню
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS menu_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    description TEXT,
                    is_available BOOLEAN DEFAULT TRUE,
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (category_id) REFERENCES menu_categories (id),
                    UNIQUE(category_id, name)
                )
            ''')
            
            conn.commit()

    def add_waiter(self, telegram_id: int, full_name: str) -> int:
        """Добавление официанта в базу"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    'INSERT OR IGNORE INTO waiters (telegram_id, full_name) VALUES (?, ?)',
                    (telegram_id, full_name)
                )
                conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                # Если официант уже существует, возвращаем его ID
                cursor.execute('SELECT id FROM waiters WHERE telegram_id = ?', (telegram_id,))
                return cursor.fetchone()[0]

    def get_waiter(self, telegram_id: int) -> Optional[Dict]:
        """Получение информации об официанте"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM waiters WHERE telegram_id = ?', (telegram_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def add_table(self, table_number: int, capacity: int = 4) -> int:
        """Добавление стола в базу"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    'INSERT OR IGNORE INTO tables (table_number, capacity) VALUES (?, ?)',
                    (table_number, capacity)
                )
                conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                cursor.execute('SELECT id FROM tables WHERE table_number = ?', (table_number,))
                return cursor.fetchone()[0]

    def get_table(self, table_number: int) -> Optional[Dict]:
        """Получение информации о столе"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM tables WHERE table_number = ?', (table_number,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_order(self, table_number: int, waiter_id: int) -> int:
        """Создание нового заказа или получение существующего активного заказа для стола"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            
            # Проверяем, есть ли уже активный заказ для этого стола
            cursor.execute(
                '''SELECT table_number FROM orders 
                   WHERE table_number = ? AND status = 'active'
                   LIMIT 1''',
                (table_number,)
            )
            existing_order = cursor.fetchone()
            if existing_order:
                # Активный заказ уже существует, возвращаем номер стола
                return table_number
            
            # Проверяем существование стола
            table = self.get_table(table_number)
            if not table:
                self.add_table(table_number)
            
            # Создаем заказ
            cursor.execute(
                '''INSERT INTO orders (table_number, waiter_id, status) 
                   VALUES (?, ?, 'active')''',
                (table_number, waiter_id)
            )
            
            # Обновляем статус стола
            cursor.execute(
                'UPDATE tables SET is_available = FALSE WHERE table_number = ?',
                (table_number,)
            )
            
            conn.commit()
            return table_number

    def add_order_item(self, table_number: int, item_name: str, item_price: float, quantity: int = 1) -> int:
        """Добавление позиции в заказ"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            
            total_price = item_price * quantity
            
            # Проверяем, есть ли уже такая позиция в заказе
            cursor.execute(
                '''SELECT quantity FROM order_items 
                   WHERE table_number = ? AND item_name = ? AND COALESCE(sent_to_kitchen, 0) = 0''',
                (table_number, item_name)
            )
            existing_item = cursor.fetchone()
            
            if existing_item:
                # Если позиция уже есть, обновляем количество
                new_quantity = existing_item[0] + quantity
                new_total_price = new_quantity * item_price
                
                cursor.execute(
                    '''UPDATE order_items SET quantity = ?, total_price = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE table_number = ? AND item_name = ? AND COALESCE(sent_to_kitchen, 0) = 0''',
                    (new_quantity, new_total_price, table_number, item_name)
                )
            else:
                # Если позиции нет, добавляем новую
                cursor.execute(
                '''INSERT INTO order_items (table_number, item_name, item_price, quantity, total_price, sent_to_kitchen)
                   VALUES (?, ?, ?, ?, ?, 0)''',
                (table_number, item_name, item_price, quantity, total_price)
                )
            
            # Обновляем общую сумму заказа
            cursor.execute(
                '''UPDATE orders SET total_amount = total_amount + ?, updated_at = CURRENT_TIMESTAMP
                   WHERE table_number = ? AND status = 'active' ''',
                (total_price, table_number)
            )
            
            conn.commit()
            return cursor.lastrowid

    def update_order_item_quantity(self, table_number: int, item_name: str, new_quantity: int) -> bool:
        """Обновление количества позиции в заказе"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            
            # Получаем текущие данные позиции
            cursor.execute(
                '''SELECT item_price, quantity FROM order_items 
                   WHERE table_number = ? AND item_name = ?''',
                (table_number, item_name)
            )
            result = cursor.fetchone()
            
            if not result:
                return False
            
            old_quantity = result[1]
            item_price = result[0]
            quantity_diff = new_quantity - old_quantity
            price_diff = quantity_diff * item_price
            
            # Обновляем количество и общую цену позиции
            cursor.execute(
                '''UPDATE order_items SET quantity = ?, total_price = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE table_number = ? AND item_name = ?''',
                (new_quantity, new_quantity * item_price, table_number, item_name)
            )
            
            # Обновляем общую сумму заказа
            cursor.execute(
                '''UPDATE orders SET total_amount = total_amount + ?, updated_at = CURRENT_TIMESTAMP
                   WHERE table_number = ? AND status = 'active' ''',
                (price_diff, table_number)
            )
            
            conn.commit()
            return True

    def remove_order_item(self, table_number: int, item_name: str) -> bool:
        """Удаление позиции из заказа"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            
            # Получаем цену удаляемой позиции
            cursor.execute(
                '''SELECT total_price FROM order_items 
                   WHERE table_number = ? AND item_name = ?''',
                (table_number, item_name)
            )
            result = cursor.fetchone()
            
            if not result:
                return False
            
            price_to_remove = result[0]
            
            # Удаляем позицию
            cursor.execute(
                'DELETE FROM order_items WHERE table_number = ? AND item_name = ?',
                (table_number, item_name)
            )
            
            # Обновляем общую сумму заказа
            cursor.execute(
                '''UPDATE orders SET total_amount = total_amount - ?, updated_at = CURRENT_TIMESTAMP
                   WHERE table_number = ? AND status = 'active' ''',
                (price_to_remove, table_number)
            )
            
            conn.commit()
            return True

    def update_order_comment(self, table_number: int, comment: str) -> bool:
        """Обновляет комментарий активного заказа"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''UPDATE orders
                   SET comment = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE table_number = ? AND status = 'active' ''',
                (comment, table_number)
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_order_waiter(self, table_number: int, waiter_id: int) -> bool:
        """Обновляет официанта для активного заказа"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''UPDATE orders
                   SET waiter_id = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE table_number = ? AND status = 'active' ''',
                (waiter_id, table_number)
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_active_order_by_table(self, table_number: int) -> Optional[Dict]:
        """Получение активного заказа по номеру стола"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT o.*, w.full_name as waiter_name
                FROM orders o
                LEFT JOIN waiters w ON o.waiter_id = w.id
                WHERE o.table_number = ? AND o.status = 'active'
                ORDER BY o.created_at DESC
                LIMIT 1
            ''', (table_number,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_active_order(self, table_number: int, waiter_id: int) -> Optional[Dict]:
        """Получение активного заказа для стола и официанта"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT o.*, w.full_name as waiter_name
                FROM orders o
                JOIN waiters w ON o.waiter_id = w.id
                WHERE o.table_number = ? AND o.waiter_id = ? AND o.status = 'active'
            ''', (table_number, waiter_id))
            
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_order_items(self, table_number: int) -> List[Dict]:
        """Получение всех позиций заказа по номеру стола"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM order_items 
                WHERE table_number = ? 
                ORDER BY created_at
            ''', (table_number,))
            return [dict(row) for row in cursor.fetchall()]

    def get_unsent_order_items(self, table_number: int) -> List[Dict]:
        """Получение текущих неотправленных/активных позиций заказа по столу"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM order_items
                WHERE table_number = ?
                  AND COALESCE(sent_to_kitchen, 0) = 0
                ORDER BY created_at
            ''', (table_number,))
            return [dict(row) for row in cursor.fetchall()]

    def get_all_active_orders(self) -> List[Dict]:
        """Получение всех активных заказов по всем официантам"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT o.*, w.full_name as waiter_name
                FROM orders o
                LEFT JOIN waiters w ON o.waiter_id = w.id
                WHERE o.status = 'active'
                ORDER BY o.created_at DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]

    def get_waiter_orders(self, waiter_id: int) -> List[Dict]:
        """Получение всех активных заказов официанта"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT o.*, w.full_name as waiter_name
                FROM orders o
                JOIN waiters w ON o.waiter_id = w.id
                WHERE o.waiter_id = ? AND o.status = 'active'
                ORDER BY o.created_at DESC
            ''', (waiter_id,))
            
            return [dict(row) for row in cursor.fetchall()]

    def complete_order(self, table_number: int) -> bool:
        """Завершение заказа"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            
            # Обновляем статус заказа
            cursor.execute(
                '''UPDATE orders SET status = 'completed', updated_at = CURRENT_TIMESTAMP
                   WHERE table_number = ? AND status = 'active' ''',
                (table_number,)
            )
            
            # Освобождаем стол
            cursor.execute(
                'UPDATE tables SET is_available = TRUE WHERE table_number = ?',
                (table_number,)
            )
            
            # Очищаем позиции заказа
            cursor.execute(
                'DELETE FROM order_items WHERE table_number = ?',
                (table_number,)
            )
            
            conn.commit()
            return True

    def cancel_order(self, table_number: int) -> bool:
        """Отмена заказа"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            
            # Обновляем статус заказа
            cursor.execute(
                '''UPDATE orders SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
                   WHERE table_number = ? AND status = 'active' ''',
                (table_number,)
            )
            
            # Освобождаем стол
            cursor.execute(
                'UPDATE tables SET is_available = TRUE WHERE table_number = ?',
                (table_number,)
            )
            
            # Очищаем позиции заказа
            cursor.execute(
                'DELETE FROM order_items WHERE table_number = ?',
                (table_number,)
            )
            
            conn.commit()
            return True

    def import_menu_from_json(self, json_data: Dict):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            
            # Очищаем таблицы
            cursor.execute('DELETE FROM menu_items')
            cursor.execute('DELETE FROM menu_categories')
            
            # Добавляем категории с порядковым номером
            categories = {}
            for cat_idx, category_data in enumerate(json_data.get('menu', [])):
                category_name = category_data['category']
                cursor.execute(
                    'INSERT INTO menu_categories (name, sort_order) VALUES (?, ?)',
                    (category_name, cat_idx)
                )
                categories[category_name] = cursor.lastrowid
            
            # Добавляем позиции меню с порядковым номером внутри категории
            for cat_idx, category_data in enumerate(json_data.get('menu', [])):
                category_name = category_data['category']
                category_id = categories[category_name]
                
                for item_idx, item in enumerate(category_data['items']):
                    cursor.execute('''
                        INSERT INTO menu_items (category_id, name, price, description, sort_order, prep_time_minutes, image)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (category_id, item['name'], item['price'], item.get('description', ''), item_idx, item.get('prep_time', 10), item.get('image', '')))
            
            conn.commit()

    def set_item_image(self, item_name: str, image_url: str):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE menu_items SET image = ? WHERE name = ?',
                (image_url, item_name)
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_menu_categories(self) -> List[str]:
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT name FROM menu_categories 
                ORDER BY sort_order
            ''')
            return [row[0] for row in cursor.fetchall()]

    def get_menu_items(self, category: str) -> List[Dict]:
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT mi.*, mc.name as category_name
                FROM menu_items mi
                JOIN menu_categories mc ON mi.category_id = mc.id
                WHERE mc.name = ? AND mi.is_available = TRUE 
                ORDER BY mi.sort_order
            ''', (category,))
            return [dict(row) for row in cursor.fetchall()]
    def calculate_order(self, table_number: int) -> bool:
        """Расчет заказа - завершение без отправки в группу"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            
            # Обновляем статус заказа
            cursor.execute(
                '''UPDATE orders SET status = 'calculated', updated_at = CURRENT_TIMESTAMP
                   WHERE table_number = ? AND status = 'active' ''',
                (table_number,)
            )
            
            # Освобождаем стол
            cursor.execute(
                'UPDATE tables SET is_available = TRUE WHERE table_number = ?',
                (table_number,)
            )
            
            # Очищаем позиции заказа
            cursor.execute(
                'DELETE FROM order_items WHERE table_number = ?',
                (table_number,)
            )
            
            conn.commit()
            return True
    def update_order_sent_to_kitchen(self, table_number: int):
        """Отмечает только новые позиции заказа как отправленные на кухню"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE order_items
                SET sent_to_kitchen = 1,
                    item_status = COALESCE(item_status, 'pending'),
                    sent_batch_at = CURRENT_TIMESTAMP
                WHERE table_number = ? AND COALESCE(sent_to_kitchen, 0) = 0
            ''', (table_number,))

            cursor.execute('''
                UPDATE orders 
                SET sent_to_kitchen_at = CURRENT_TIMESTAMP, 
                    kitchen_status = 'new',
                    updated_at = CURRENT_TIMESTAMP
                WHERE table_number = ? AND status = 'active'
            ''', (table_number,))
            conn.commit()

    def get_kitchen_orders(self, status_filter=None):
        """Получает заказы для кухни, сгруппированные по батчам отправки"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = '''
                SELECT o.*, w.full_name as waiter_name
                FROM orders o
                JOIN waiters w ON o.waiter_id = w.id
                WHERE o.status = 'active' 
                  AND o.sent_to_kitchen_at IS NOT NULL
            '''
            
            if status_filter:
                query += f" AND o.kitchen_status = '{status_filter}'"
            
            query += ' ORDER BY o.sent_to_kitchen_at ASC'
            
            cursor.execute(query)
            rows = [dict(row) for row in cursor.fetchall()]
            
            # Берём последний активный заказ на стол (на случай дублей)
            orders_by_table = {}
            for row in rows:
                tn = row['table_number']
                prev = orders_by_table.get(tn)
                if prev is None or row['id'] > prev['id']:
                    orders_by_table[tn] = row
            
            result = []
            for order in orders_by_table.values():
                batches = self.get_order_batches(order['table_number'])
                for batch in batches:
                    entry = {**order, 'items': batch['items'], 'sent_to_kitchen_at': batch['sent_at']}
                    result.append(entry)
                
            return result

    def get_order_batches(self, table_number: int):
        """Группирует позиции заказа по батчам отправки на кухню"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT DISTINCT COALESCE(sent_batch_at, created_at) as batch_key
                FROM order_items
                WHERE table_number = ?
                  AND COALESCE(sent_to_kitchen, 0) = 1
                ORDER BY batch_key
            ''', (table_number,))
            
            batches = []
            for row in cursor.fetchall():
                batch_key = row['batch_key']
                cursor.execute('''
                    SELECT oi.*, 
                           COALESCE(oi.prep_time_minutes, 10) as prep_time_minutes,
                           COALESCE(oi.item_status, 'pending') as item_status
                    FROM order_items oi
                    WHERE oi.table_number = ?
                      AND COALESCE(oi.sent_to_kitchen, 0) = 1
                      AND COALESCE(oi.sent_batch_at, oi.created_at) = ?
                    ORDER BY oi.created_at
                ''', (table_number, batch_key))
                
                items = [dict(r) for r in cursor.fetchall()]
                if items:
                    batches.append({
                        'sent_at': batch_key,
                        'items': items
                    })
            
            return batches

    def get_kitchen_order_items(self, table_number: int):
        """Получает все отправленные позиции заказа для истории"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT oi.*, 
                       COALESCE(oi.prep_time_minutes, 10) as prep_time_minutes,
                       COALESCE(oi.item_status, 'pending') as item_status
                FROM order_items oi
                WHERE oi.table_number = ?
                  AND COALESCE(oi.sent_to_kitchen, 0) = 1
                ORDER BY oi.created_at
            ''', (table_number,))
            
            return [dict(row) for row in cursor.fetchall()]

    def update_item_status(self, table_number: int, item_name: str, status: str):
        """Обновляет статус позиции заказа"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            
            if status == 'cooking':
                cursor.execute('''
                    UPDATE order_items 
                    SET item_status = ?, started_at = CURRENT_TIMESTAMP
                    WHERE table_number = ? AND item_name = ?
                ''', (status, table_number, item_name))
            elif status == 'ready':
                cursor.execute('''
                    UPDATE order_items 
                    SET item_status = ?, ready_at = CURRENT_TIMESTAMP
                    WHERE table_number = ? AND item_name = ?
                ''', (status, table_number, item_name))
            else:
                cursor.execute('''
                    UPDATE order_items 
                    SET item_status = ?
                    WHERE table_number = ? AND item_name = ?
                ''', (status, table_number, item_name))
            
            conn.commit()
            
            # Проверяем, все ли позиции готовы
            cursor.execute('''
                SELECT COUNT(*) as total, 
                       SUM(CASE WHEN item_status = 'ready' THEN 1 ELSE 0 END) as ready
                FROM order_items 
                WHERE table_number = ?
            ''', (table_number,))
            
            result = cursor.fetchone()
            if result[0] == result[1] and result[0] > 0:
                # Все позиции готовы - обновляем статус заказа
                cursor.execute('''
                    UPDATE orders 
                    SET kitchen_status = 'ready'
                    WHERE table_number = ? AND status = 'active'
                ''', (table_number,))
                conn.commit()

    def update_item_status_by_id(self, item_id: int, status: str):
        """Обновляет статус позиции заказа по уникальному ID"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()

            cursor.execute('SELECT table_number FROM order_items WHERE id = ?', (item_id,))
            row = cursor.fetchone()
            if not row:
                return False

            table_number = row[0]

            if status == 'cooking':
                cursor.execute('''
                    UPDATE order_items 
                    SET item_status = ?, started_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (status, item_id))
            elif status == 'ready':
                cursor.execute('''
                    UPDATE order_items 
                    SET item_status = ?, ready_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (status, item_id))
            else:
                cursor.execute('''
                    UPDATE order_items 
                    SET item_status = ?
                    WHERE id = ?
                ''', (status, item_id))

            conn.commit()

            cursor.execute('''
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN item_status = 'ready' THEN 1 ELSE 0 END) as ready
                FROM order_items
                WHERE table_number = ?
            ''', (table_number,))

            result = cursor.fetchone()
            if result[0] == result[1] and result[0] > 0:
                cursor.execute('''
                    UPDATE orders
                    SET kitchen_status = 'ready'
                    WHERE table_number = ? AND status = 'active'
                ''', (table_number,))
                conn.commit()

            return True

    def update_order_kitchen_status(self, table_number: int, status: str):
        """Обновляет статус заказа на кухне"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE orders 
                SET kitchen_status = ?
                WHERE table_number = ? AND status = 'active'
            ''', (status, table_number))
            conn.commit()

    def get_completed_orders(self, limit=50):
        """Получает завершенные заказы для истории"""
        with sqlite3.connect(self.db_name) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT o.*, w.full_name as waiter_name
                FROM orders o
                JOIN waiters w ON o.waiter_id = w.id
                WHERE o.status IN ('completed', 'cancelled')
                ORDER BY o.updated_at DESC
                LIMIT ?
            ''', (limit,))
            
            orders = [dict(row) for row in cursor.fetchall()]
            
            for order in orders:
                order['items'] = self.get_kitchen_order_items(order['table_number'])
                
            return orders

    def get_menu_item_prep_time(self, item_name: str) -> int:
        """Получает время приготовления блюда из меню"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT prep_time_minutes FROM menu_items 
                WHERE name = ?
            ''', (item_name,))
            result = cursor.fetchone()
            return result[0] if result and result[0] else 10

    # В db.py добавить:
    def update_item_prep_time(self, table_number: int, item_name: str, prep_time: int):
        """Обновляет время приготовления позиции заказа"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE order_items 
                SET prep_time_minutes = ?
                WHERE table_number = ? AND item_name = ? AND COALESCE(sent_to_kitchen, 0) = 0
            ''', (prep_time, table_number, item_name))
            conn.commit()

# Создаем глобальный экземпляр базы данных
db = Database()