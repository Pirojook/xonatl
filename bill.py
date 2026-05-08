import sqlite3
import datetime
from pathlib import Path

# Конфигурация
DB_PATH = 'restaurant.db'

# Константы для расчетов
DISCOUNT_RATE = 0.00
SERVICE_RATE = 0.00
VAT_RATE = 0.0


def get_order_items(table_number):
    """Получает позиции заказа для указанного стола"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT item_name, quantity, item_price, total_price, id
        FROM order_items 
        WHERE table_number = ? 
        ORDER BY item_name
    """, (table_number,))

    items = cursor.fetchall()
    conn.close()
    return items


def get_order_summary(table_number):
    """Получает общую информацию о заказе"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            SUM(quantity) as total_items,
            SUM(total_price) as subtotal
        FROM order_items 
        WHERE table_number = ?
    """, (table_number,))

    result = cursor.fetchone()
    conn.close()

    return {
        'total_items': result[0] if result[0] else 0,
        'subtotal': result[1] if result[1] else 0
    }


def format_money(value):
    return f"{value:,.0f} UZS".replace(',', ' ')


def format_money_hype(value):
    return f"{value:,.0f}".replace(',', ' ')


def generate_html_bill(table_number):
    """Генерирует HTML чек под 56 мм"""

    order_items = get_order_items(table_number)
    order_summary = get_order_summary(table_number)

    id_table = ""
    for item in order_items:
        id_table = item["id"]

    subtotal = order_summary['subtotal']
    discount = subtotal * DISCOUNT_RATE
    after_discount = subtotal - discount
    service = after_discount * SERVICE_RATE
    vat = (after_discount + service) * VAT_RATE
    grand_total = after_discount + service + vat

    now = datetime.datetime.now()
    date_str = now.strftime("%d.%m.%Y %H:%M")

    html_template = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Чек ресторана</title>

<style>
:root{{
  --accent:#111827;
  --muted:#6b7280;
  --border:#e5e7eb;
  --bg:#ffffff;
}}

*{{box-sizing:border-box; margin:0; padding:0;}}

body{{
  margin:0;
  padding:0;
  background:#f3f4f6;
  color:#111827;
  font:12px/1.35 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
}}

@font-face {{
  font-family: 'Pehlevi';
  src: url('https://fonts-online.ru/fonts/pehlevi.woff2') format('woff2'),
       url('https://fonts-online.ru/fonts/pehlevi.woff') format('woff'),
       url('https://fonts-online.ru/fonts/pehlevi.ttf') format('truetype');
  font-weight: normal;
  font-style: normal;
  font-display: swap;
}}

.page{{
  width:48mm;
  max-width:48mm;
  margin:0 auto;
  background:var(--bg);
  border:none;
  border-radius:0;
  box-shadow:none;
  overflow:hidden;
}}

header{{
  text-align:center;
  padding:6px 6px;
  border-bottom:1px dashed var(--border);
}}

header img{{
  max-width:110px;
}}

header h1{{
  margin:4px 0 0;
  font-size:22px;
  color:var(--accent);
  font-family:'Pehlevi', serif;
  line-height:1.1;
}}

header .meta{{
  margin-top:2px;
  color:var(--muted);
  font-size:9px;
}}

.section{{padding:4px 4px;}}

#details .row{{
  display:flex;
  justify-content:space-between;
  font-size:10px;
  padding:1px 0;
}}

#details .label{{
  color:var(--muted);
}}

table{{
  width:100%;
  border-collapse:collapse;
  font-size:10px;
}}

thead th{{
  text-align:left;
  font-weight:600;
  color:var(--muted);
  border-bottom:1px solid var(--border);
  padding:2px 0;
}}

tbody td{{
  padding:2px 0;
  border-bottom:1px dashed var(--border);
  vertical-align:top;
}}

.name{{width:42%; word-break:break-word;}}
.price{{width:18%; text-align:right;}}
.qty{{width:15%; text-align:center;}}
.total{{width:25%; text-align:right;}}

.summary .row{{
  display:flex;
  justify-content:space-between;
  font-size:10px;
  padding:1px 0;
  border-bottom: none;
}}

.summary .row.total{{

  margin-left:-6px;
  margin-right:-6px;

  padding:6px;

  font-weight:700;
  font-size:14px;

  display:flex;
  justify-content:space-between;
  width:calc(100% + 12px);
}}


.summary .row.total > div{{
  display:block;
}}


.summary .row.total > div:first-child{{
  text-align:left;
  white-space:nowrap;
}}

.summary .row.total > div:last-child{{
  margin-left:auto;
  text-align:right;
  white-space:nowrap;
}}

.summary{{
  margin-top:6px;
  border-top:2px solid #000;
  padding-top:4px;
}}



.note{{
  margin-top:6px;
  color:var(--muted);
  font-size:10px;
  text-align:center;
}}

footer{{
  padding:4px 6px 8px;
  text-align:center;
  color:var(--muted);
  font-size:8px;
  border-top:1px dashed var(--border);
}}

.actions{{
  display:flex;
  justify-content:center;
  padding:10px;
}}

.btn{{
  cursor:pointer;
  border:1px solid var(--border);
  background:#fff;
  border-radius:6px;
  padding:6px 10px;
  font-size:12px;
}}

@media print{{

  @page {{
    size: 58mm auto;
    margin: 0mm;
  }}

  * {{
    margin:0 !important;
    padding:0 !important;
    box-sizing: border-box !important;
  }}

  body{{
    background:#fff !important;
    width: 58mm !important;
    margin: 0 !important;
    padding: 0 !important;
  }}

  .page{{
    width: 58mm !important;
    max-width: 58mm !important;
    margin: 0 !important;
    padding: 0 !important;
    border:none;
    box-shadow:none;
    border-radius:0;
  }}

  /* Восстанавливаем нужные отступы внутри секций после общего сброса */
  header{{
    padding: 6px 6px !important;
    border-bottom:1px dashed var(--border);
  }}

  .section{{
    padding: 4px 4px !important;
  }}

  footer{{
    padding: 4px 6px 8px !important;
    border-top:1px dashed var(--border);
  }}

  thead th{{
    padding: 2px 0 !important;
  }}

  tbody td{{
    padding: 2px 0 !important;
  }}

  .summary{{
    margin-top: 6px !important;
    padding-top: 4px !important;
  }}

  .summary .row.total{{
    margin-left: -6px !important;
    margin-right: -6px !important;
    padding: 6px !important;
    width: calc(100% + 12px) !important;
  }}

  .actions{{
    display:none;
  }}
}}
</style>
</head>
<body>

<div class="page" id="bill">

<header>
  <img src="https://i.ibb.co/B2BxXLPv/Xon-Atlas.png">
  <h1>Xon Atlas</h1>
  <div class="meta">Bukhara • 8 Kh. Ibadov St. • +998907108276</div>
</header>

<section class="section" id="details">
  <div class="row"><div class="label">Date</div><div>{date_str}</div></div>
  <div class="row"><div class="label">Table</div><div>{table_number}</div></div>
  <div class="row"><div class="label">Waiter</div><div>Samir</div></div>
  <div class="row"><div class="label">Order №</div><div>{id_table}</div></div>
</section>

<section class="section">
<table>
<thead>
<tr>
  <th class="name">Name</th>
  <th class="price">Price</th>
  <th class="qty">Qty</th>
  <th class="total">Sum</th>
</tr>
</thead>
<tbody>
"""

    for item in order_items:
        html_template += f"""
<tr>
  <td class="name">{item['item_name']}</td>
  <td class="price">{format_money_hype(item['item_price'])}</td>
  <td class="qty">{item['quantity']}</td>
  <td class="total">{format_money_hype(item['total_price'])}</td>
</tr>
"""

    html_template += f"""
</tbody>
</table>

<div class="summary">
  <div class="row total">
    <div>TOTAL</div>
    <div>{format_money(grand_total)}</div>
  </div>
</div>

<footer>
  <div style="margin:6px 0;">
    <img
      src="https://i.ibb.co/1tTfk29z/qrcode.png"
      style="width:110px;height:auto;">
  </div>
  <div class="note">Thank you for being with us!</div>
</footer>

</section>
</div>

<div class="actions">
  <button class="btn" onclick="window.print()">Печать</button>
</div>

</body>
</html>
"""

    return html_template


def billing(table_number):
    try:
        html_content = generate_html_bill(table_number)

        output_file = f"bill_table_{table_number}.html"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"Чек успешно сгенерирован: {output_file}")

    except sqlite3.Error as e:
        print(f"Ошибка базы данных: {e}")
    except Exception as e:
        print(f"Ошибка: {e}")


if __name__ == "__main__":
    table = input("Введите номер стола: ")
    billing(table)