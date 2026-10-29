"""
Сервис A — каталог товаров (порт 5001).

    POST /products        создать товар {"name": "Мышь", "price": 5000}  -> 201
    GET  /products/<id>   получить товар                                -> 200 / 404

Данные хранятся в памяти процесса.
Запуск: python catalog_service.py --port 5001
"""

import argparse
import threading

from flask import Flask, jsonify, request

app = Flask(__name__)
app.json.ensure_ascii = False
app.json.sort_keys = False

products = {}
next_id = 1
lock = threading.Lock()


def error(status, message):
    """Ошибка в едином JSON-формате."""
    return jsonify({"error": message}), status


@app.post("/products")
def create_product():
    global next_id
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error(400, "Тело запроса должно быть JSON-объектом")

    name = data.get("name")
    price = data.get("price")
    if not isinstance(name, str) or not name.strip():
        return error(400, "Поле name обязательно и должно быть непустой строкой")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or price <= 0:
        return error(400, "Поле price обязательно и должно быть положительным числом")

    with lock:
        product = {"id": next_id, "name": name.strip(), "price": price}
        products[next_id] = product
        next_id += 1

    app.logger.info("Создан товар %s", product)
    return jsonify(product), 201


@app.get("/products/<int:product_id>")
def get_product(product_id):
    with lock:
        product = products.get(product_id)
    if product is None:
        return error(404, "Товар с id=%d не найден" % product_id)
    return jsonify(product)


@app.errorhandler(404)
def not_found(e):
    return error(404, "Адрес не найден: %s" % request.path)


@app.errorhandler(405)
def method_not_allowed(e):
    return error(405, "Метод %s не поддерживается для %s" % (request.method, request.path))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Сервис A — каталог товаров")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5001)
    args = parser.parse_args()
    app.logger.setLevel("INFO")
    app.run(host=args.host, port=args.port, threaded=True)
