"""
Сервис B — заказы (порт 5002).

    POST /orders        создать заказ {"product_id": 1, "quantity": 3}  -> 201
    GET  /orders/<id>   получить сохранённый заказ                     -> 200 / 404

При создании заказа B запрашивает товар у сервиса A (каталога) по HTTP,
считает сумму и сохраняет в заказе название и цену товара. Поэтому сохранённый
заказ можно получить, даже когда A выключен.

Запуск: python orders_service.py --port 5002 --catalog-url http://127.0.0.1:5001
"""

import argparse
import threading

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
app.json.ensure_ascii = False
app.json.sort_keys = False

CATALOG_URL = "http://127.0.0.1:5001"
CATALOG_TIMEOUT = 2.0

orders = {}
next_id = 1
lock = threading.Lock()


def error(status, message):
    """Ошибка в едином JSON-формате."""
    return jsonify({"error": message}), status


def is_positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


@app.post("/orders")
def create_order():
    global next_id
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error(400, "Тело запроса должно быть JSON-объектом")

    product_id = data.get("product_id")
    quantity = data.get("quantity")
    if not is_positive_int(product_id):
        return error(400, "Поле product_id обязательно и должно быть целым числом больше 0")
    if not is_positive_int(quantity):
        return error(400, "Поле quantity обязательно и должно быть целым числом больше 0")

    url = "%s/products/%d" % (CATALOG_URL, product_id)
    try:
        response = requests.get(url, timeout=CATALOG_TIMEOUT)
    except requests.exceptions.ConnectionError:
        app.logger.warning("Каталог недоступен: %s", url)
        return error(503, "Сервис каталога недоступен, попробуйте позже")
    except requests.exceptions.Timeout:
        app.logger.warning("Каталог не ответил за %.1f с: %s", CATALOG_TIMEOUT, url)
        return error(503, "Сервис каталога не ответил за %.0f с, попробуйте позже" % CATALOG_TIMEOUT)

    if response.status_code == 404:
        return error(404, "Товар с id=%d не найден в каталоге" % product_id)
    if response.status_code != 200:
        app.logger.warning("Каталог ответил кодом %d: %s", response.status_code, url)
        return error(502, "Сервис каталога вернул ошибку %d" % response.status_code)

    product = response.json()

    with lock:
        order = {
            "id": next_id,
            "product_id": product_id,
            "name": product["name"],
            "price": product["price"],
            "quantity": quantity,
            "total": round(product["price"] * quantity, 2),
        }
        orders[next_id] = order
        next_id += 1

    app.logger.info("Создан заказ %s", order)
    return jsonify(order), 201


@app.get("/orders/<int:order_id>")
def get_order(order_id):
    with lock:
        order = orders.get(order_id)
    if order is None:
        return error(404, "Заказ с id=%d не найден" % order_id)
    return jsonify(order)


@app.errorhandler(404)
def not_found(e):
    return error(404, "Адрес не найден: %s" % request.path)


@app.errorhandler(405)
def method_not_allowed(e):
    return error(405, "Метод %s не поддерживается для %s" % (request.method, request.path))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Сервис B — заказы")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5002)
    parser.add_argument("--catalog-url", default=CATALOG_URL, help="адрес сервиса A")
    parser.add_argument("--timeout", type=float, default=CATALOG_TIMEOUT,
                        help="таймаут запроса к сервису A, с")
    args = parser.parse_args()
    CATALOG_URL = args.catalog_url.rstrip("/")
    CATALOG_TIMEOUT = args.timeout
    app.logger.setLevel("INFO")
    app.run(host=args.host, port=args.port, threaded=True)
