import os
import sys
import json
import random
import datetime
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
import pymysql

PORT = 3000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'project',
    'charset': 'utf8mb4',
    'autocommit': True
}

def get_db():
    try:
        return pymysql.connect(**DB_CONFIG)
    except Exception as e:
        print(f"[MySQL Connection Error]: {e}", flush=True)
        return None

class FoodDeliveryHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/api/orders':
            self.handle_get_orders()
        elif path == '/api/stats':
            self.handle_get_stats()
        elif path == '/api/test-db':
            self.handle_test_db()
        else:
            # Default static file handling
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ['/api/order', '/submit_payment']:
            self.handle_create_order()
        else:
            self.send_error(404, "Endpoint not found")

    def handle_test_db(self):
        conn = get_db()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM CUSTOMER")
            cust_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM ORDERS")
            ord_count = cur.fetchone()[0]
            conn.close()
            self.send_json_response(200, {
                "status": "connected",
                "database": "project",
                "customer_count": cust_count,
                "order_count": ord_count
            })
        else:
            self.send_json_response(500, {
                "status": "error",
                "message": "Cannot connect to MySQL database 'project' on localhost:3306"
            })

    def handle_get_orders(self):
        conn = get_db()
        if not conn:
            self.send_json_response(500, {"error": "Database connection failed"})
            return

        try:
            cur = conn.cursor(pymysql.cursors.DictCursor)
            query = """
            SELECT 
                o.order_id,
                o.order_date,
                o.order_time,
                o.total_amount,
                o.delivery_time,
                c.customer_id,
                CONCAT(c.First_name, ' ', COALESCE(c.Middle_name, ''), ' ', COALESCE(c.Last_name, '')) AS customer_name,
                c.email_id,
                c.mobile_no,
                ca.address,
                r.res_name AS restaurant_name,
                dp.dev_name AS delivery_partner_name,
                dp.mobile_num AS delivery_partner_phone,
                p.payment_method,
                p.payment_id
            FROM ORDERS o
            LEFT JOIN CUSTOMER c ON o.customer_id = c.customer_id
            LEFT JOIN CUST_ADDRESS ca ON c.customer_id = ca.customer_id
            LEFT JOIN RESTAURANT r ON o.restaurant_id = r.restaurant_id
            LEFT JOIN DELIVERY_PARTNERS dp ON o.id_number = dp.id_number
            LEFT JOIN PAYMENT p ON o.order_id = p.order_id
            ORDER BY CAST(o.order_id AS UNSIGNED) DESC
            LIMIT 50
            """
            cur.execute(query)
            rows = cur.fetchall()
            for r in rows:
                if isinstance(r.get('order_date'), (datetime.date, datetime.datetime)):
                    r['order_date'] = str(r['order_date'])
                if isinstance(r.get('total_amount'), float):
                    r['total_amount'] = round(r['total_amount'], 2)
            conn.close()
            self.send_json_response(200, {"success": True, "orders": rows})
        except Exception as e:
            if conn: conn.close()
            self.send_json_response(500, {"error": str(e)})

    def handle_get_stats(self):
        conn = get_db()
        if not conn:
            self.send_json_response(500, {"error": "Database connection failed"})
            return
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM CUSTOMER")
            cust_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM ORDERS")
            ord_row = cur.fetchone()
            ord_count, total_sales = ord_row[0], float(ord_row[1])
            cur.execute("SELECT COUNT(*) FROM RESTAURANT")
            res_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM DELIVERY_PARTNERS")
            del_count = cur.fetchone()[0]
            conn.close()
            self.send_json_response(200, {
                "success": True,
                "customers": cust_count,
                "orders": ord_count,
                "total_sales": round(total_sales, 2),
                "restaurants": res_count,
                "delivery_partners": del_count
            })
        except Exception as e:
            if conn: conn.close()
            self.send_json_response(500, {"error": str(e)})

    def handle_create_order(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8')
        content_type = self.headers.get('Content-Type', '')

        data = {}
        if 'application/json' in content_type:
            try:
                data = json.loads(body)
            except Exception:
                data = {}
        else:
            parsed = urllib.parse.parse_qs(body)
            for k, v in parsed.items():
                data[k] = v[0] if len(v) == 1 else v

        name = data.get('name', 'Customer').strip()
        email = data.get('email', 'customer@example.com').strip()
        pnum = data.get('pnum', '9876543210').strip()
        apnum = data.get('apnum', '').strip()
        address = data.get('address', 'Delivery Address').strip()
        payment_method = data.get('pay', data.get('pay_method', 'Cash on Delivery')).strip()
        if not payment_method:
            payment_method = 'Cash on Delivery'

        amount_str = data.get('amount', '450.00')
        try:
            amount = float(amount_str)
        except Exception:
            amount = 450.00

        restaurant_id = data.get('restaurant_id', None)

        conn = get_db()
        if not conn:
            self.send_json_response(500, {
                "success": False,
                "message": "MySQL database connection failed. Make sure MySQL is running in XAMPP."
            })
            return

        try:
            cur = conn.cursor()

            # 1. Parse Name
            name_parts = name.split()
            first_name = name_parts[0] if len(name_parts) > 0 else 'Guest'
            middle_name = name_parts[1] if len(name_parts) > 2 else ''
            last_name = name_parts[-1] if len(name_parts) > 1 else (name_parts[1] if len(name_parts) == 2 else '')

            # 2. Get Next Customer ID
            cur.execute("SELECT COALESCE(MAX(customer_id), 0) + 1 FROM CUSTOMER")
            customer_id = cur.fetchone()[0]

            # 3. Insert into CUSTOMER
            cur.execute(
                "INSERT INTO CUSTOMER (customer_id, First_name, Middle_name, Last_name, email_id, mobile_no) VALUES (%s, %s, %s, %s, %s, %s)",
                (customer_id, first_name[:50], middle_name[:50], last_name[:50], email[:100], pnum[:30])
            )

            # 4. Insert into CUST_ADDRESS
            cur.execute(
                "INSERT INTO CUST_ADDRESS (address, customer_id) VALUES (%s, %s)",
                (address[:255], customer_id)
            )

            # 5. Get Next Order ID
            cur.execute("SELECT COALESCE(MAX(CAST(order_id AS UNSIGNED)), 420) + 1 FROM ORDERS")
            order_id = str(cur.fetchone()[0])

            # 6. Assign Delivery Partner
            cur.execute("SELECT id_number, dev_name, mobile_num FROM DELIVERY_PARTNERS ORDER BY RAND() LIMIT 1")
            partner = cur.fetchone()
            if partner:
                partner_id, partner_name, partner_phone = partner[0], partner[1], partner[2]
            else:
                partner_id, partner_name, partner_phone = 20231, 'John', '9988337462'

            # 7. Assign Restaurant
            if restaurant_id:
                cur.execute("SELECT restaurant_id, res_name FROM RESTAURANT WHERE restaurant_id = %s", (restaurant_id,))
                res = cur.fetchone()
            else:
                res = None
            if not res:
                cur.execute("SELECT restaurant_id, res_name FROM RESTAURANT ORDER BY RAND() LIMIT 1")
                res = cur.fetchone()
            
            res_id = res[0] if res else 1101
            res_name = res[1] if res else 'Kitchenadda'

            # 8. Time calculations
            now = datetime.datetime.now()
            order_date = now.strftime('%Y-%m-%d')
            order_time = now.strftime('%H:%M')
            delivery_time = (now + datetime.timedelta(minutes=30)).strftime('%H:%M')

            # 9. Insert into ORDERS
            cur.execute(
                "INSERT INTO ORDERS (order_id, order_time, order_date, total_amount, delivery_time, customer_id, id_number, restaurant_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (order_id, order_time, order_date, amount, delivery_time, customer_id, partner_id, res_id)
            )

            # 10. Get Next Payment ID & Insert into PAYMENT
            cur.execute("SELECT COALESCE(MAX(CAST(payment_id AS UNSIGNED)), 10020) + 1 FROM PAYMENT")
            payment_id = str(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO PAYMENT (payment_method, payment_id, amount, customer_id, order_id, restaurant_id) VALUES (%s, %s, %s, %s, %s, %s)",
                (payment_method[:50], payment_id, amount, customer_id, order_id, res_id)
            )

            conn.close()

            result = {
                "success": True,
                "order_id": order_id,
                "customer_id": customer_id,
                "customer_name": f"{first_name} {last_name}".strip(),
                "partner_name": partner_name,
                "partner_phone": partner_phone,
                "restaurant_name": res_name,
                "order_time": order_time,
                "delivery_time": delivery_time,
                "amount": amount,
                "payment_method": payment_method,
                "payment_id": payment_id,
                "message": f"Order #{order_id} placed and saved to MySQL table 'ORDERS', 'CUSTOMER', and 'PAYMENT' successfully!"
            }

            # If standard browser HTML form submission, redirect to confirm_page.html with params
            accept_header = self.headers.get('Accept', '')
            if 'text/html' in accept_header and 'application/json' not in content_type:
                qparams = urllib.parse.urlencode({
                    'order_id': order_id,
                    'customer_name': f"{first_name} {last_name}".strip(),
                    'partner_name': partner_name,
                    'amount': amount,
                    'delivery_time': delivery_time
                })
                self.send_response(303)
                self.send_header('Location', f'/DBMS/confirm_page.html?{qparams}')
                self.end_headers()
                return

            self.send_json_response(200, result)

        except Exception as e:
            if conn: conn.close()
            print(f"[Error creating order]: {e}", flush=True)
            self.send_json_response(500, {"success": False, "error": str(e)})

    def send_json_response(self, code, data):
        body = json.dumps(data).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

def run():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, FoodDeliveryHandler)
    print(f"[Food Delivery Server] Running on http://localhost:{PORT}", flush=True)
    print(f"[Database] MySQL 'project' on localhost:3306", flush=True)
    httpd.serve_forever()

if __name__ == '__main__':
    run()
