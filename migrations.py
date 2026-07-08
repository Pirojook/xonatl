# migrations.py
import sqlite3
import logging

logging.basicConfig(level=logging.INFO)

def run_migrations(db_path='restaurant.db'):
    """Выполняет миграции базы данных"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Проверяем и добавляем новые колонки в menu_items
    cursor.execute("PRAGMA table_info(menu_items)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'prep_time_minutes' not in columns:
        cursor.execute('ALTER TABLE menu_items ADD COLUMN prep_time_minutes INTEGER DEFAULT 10')
        logging.info("✅ Добавлена колонка prep_time_minutes в menu_items")
    
    if 'image' not in columns:
        cursor.execute("ALTER TABLE menu_items ADD COLUMN image TEXT DEFAULT ''")
        logging.info("✅ Добавлена колонка image в menu_items")
    
    # Проверяем и добавляем новые колонки в orders
    cursor.execute("PRAGMA table_info(orders)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'sent_to_kitchen_at' not in columns:
        cursor.execute('ALTER TABLE orders ADD COLUMN sent_to_kitchen_at TIMESTAMP')
        logging.info("✅ Добавлена колонка sent_to_kitchen_at в orders")
    
    if 'completed_at' not in columns:
        cursor.execute('ALTER TABLE orders ADD COLUMN completed_at TIMESTAMP')
        logging.info("✅ Добавлена колонка completed_at в orders")
    
    if 'kitchen_status' not in columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN kitchen_status TEXT DEFAULT 'new'")
        logging.info("✅ Добавлена колонка kitchen_status в orders")

    if 'comment' not in columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN comment TEXT DEFAULT ''")
        logging.info("✅ Добавлена колонка comment в orders")
    
    # Проверяем и добавляем новые колонки в order_items
    cursor.execute("PRAGMA table_info(order_items)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'prep_time_minutes' not in columns:
        cursor.execute('ALTER TABLE order_items ADD COLUMN prep_time_minutes INTEGER DEFAULT 10')
        logging.info("✅ Добавлена колонка prep_time_minutes в order_items")
    
    if 'item_status' not in columns:
        cursor.execute("ALTER TABLE order_items ADD COLUMN item_status TEXT DEFAULT 'pending'")
        logging.info("✅ Добавлена колонка item_status в order_items")
    
    if 'started_at' not in columns:
        cursor.execute('ALTER TABLE order_items ADD COLUMN started_at TIMESTAMP')
        logging.info("✅ Добавлена колонка started_at в order_items")
    
    if 'ready_at' not in columns:
        cursor.execute('ALTER TABLE order_items ADD COLUMN ready_at TIMESTAMP')
        logging.info("✅ Добавлена колонка ready_at в order_items")

    if 'sent_to_kitchen' not in columns:
        cursor.execute('ALTER TABLE order_items ADD COLUMN sent_to_kitchen INTEGER DEFAULT 0')
        logging.info("✅ Добавлена колонка sent_to_kitchen в order_items")
    
    if 'sent_batch_at' not in columns:
        cursor.execute('ALTER TABLE order_items ADD COLUMN sent_batch_at TIMESTAMP')
        logging.info("✅ Добавлена колонка sent_batch_at в order_items")
        # Группируем все старые отправленные позиции в один батч по столу
        cursor.execute('''
            UPDATE order_items 
            SET sent_batch_at = (
                SELECT MIN(created_at) FROM order_items AS oi2
                WHERE oi2.table_number = order_items.table_number
                  AND COALESCE(oi2.sent_to_kitchen, 0) = 1
            )
            WHERE COALESCE(sent_to_kitchen, 0) = 1 AND sent_batch_at IS NULL
        ''')
        logging.info("✅ Старые отправленные позиции сгруппированы в один батч на стол")
    
    conn.commit()
    conn.close()
    logging.info("✅ Все миграции выполнены успешно!")

if __name__ == '__main__':
    run_migrations()