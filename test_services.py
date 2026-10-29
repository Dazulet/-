"""
Автотесты: сервисы запускаются настоящими отдельными процессами на свободных портах.

    python -m unittest -v test_services
"""

import socket
import subprocess
import sys
import threading
import time
import unittest

import requests

PY = sys.executable


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start(script, *args):
    """Запустить сервис и дождаться, пока он начнёт отвечать."""
    port = free_port()
    proc = subprocess.Popen([PY, script, "--port", str(port), *args],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:%d" % port
    for _ in range(100):
        try:
            requests.get(base + "/ready-check", timeout=0.5)
            return proc, base
        except requests.exceptions.ConnectionError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("сервис %s не запустился" % script)


def stop(proc):
    proc.kill()
    proc.wait()


class ThreeChecks(unittest.TestCase):
    """Три проверки из задания — на одной паре сервисов, по порядку."""

    def test_three_checks(self):
        catalog, a = start("catalog_service.py")
        orders, b = start("orders_service.py", "--catalog-url", a)
        try:
            r = requests.post(a + "/products", json={"name": "Мышь", "price": 5000})
            self.assertEqual(r.status_code, 201)
            pid = r.json()["id"]
            r = requests.post(b + "/orders", json={"product_id": pid, "quantity": 3})
            self.assertEqual(r.status_code, 201)
            order = r.json()
            self.assertEqual(order, {"id": 1, "product_id": pid, "name": "Мышь",
                                     "price": 5000, "quantity": 3, "total": 15000})

            stop(catalog)
            r = requests.post(b + "/orders", json={"product_id": pid, "quantity": 1})
            self.assertEqual(r.status_code, 503)
            self.assertIn("error", r.json())
            self.assertIn("недоступен", r.json()["error"])

            r = requests.get(b + "/orders/1")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json(), order)
        finally:
            stop(orders)
            if catalog.poll() is None:
                stop(catalog)


class Errors(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.catalog, cls.a = start("catalog_service.py")
        cls.orders, cls.b = start("orders_service.py", "--catalog-url", cls.a)

    @classmethod
    def tearDownClass(cls):
        stop(cls.orders)
        stop(cls.catalog)

    def test_unknown_product_is_404(self):
        r = requests.post(self.b + "/orders", json={"product_id": 999, "quantity": 1})
        self.assertEqual(r.status_code, 404)
        self.assertIn("не найден", r.json()["error"])

    def test_unknown_order_is_404(self):
        self.assertEqual(requests.get(self.b + "/orders/999").status_code, 404)

    def test_bad_order_body_is_400(self):
        for body in ({}, {"product_id": 1}, {"product_id": 1, "quantity": 0},
                     {"product_id": "1", "quantity": 2}):
            self.assertEqual(requests.post(self.b + "/orders", json=body).status_code, 400, body)

    def test_bad_product_body_is_400(self):
        for body in ({}, {"name": "", "price": 10}, {"name": "x", "price": -5},
                     {"name": "x", "price": "100"}):
            self.assertEqual(requests.post(self.a + "/products", json=body).status_code, 400, body)

    def test_unknown_product_in_catalog_is_404(self):
        self.assertEqual(requests.get(self.a + "/products/999").status_code, 404)


class HangingCatalog(unittest.TestCase):

    def test_timeout_when_catalog_hangs(self):
        """A принимает подключение, но не отвечает: B ждёт не дольше таймаута и отдаёт 503."""
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        hanging = []
        threading.Thread(target=lambda: hanging.append(listener.accept()), daemon=True).start()
        url = "http://127.0.0.1:%d" % listener.getsockname()[1]

        orders, b = start("orders_service.py", "--catalog-url", url, "--timeout", "1")
        try:
            started = time.time()
            r = requests.post(b + "/orders", json={"product_id": 1, "quantity": 1}, timeout=10)
            elapsed = time.time() - started
            self.assertEqual(r.status_code, 503)
            self.assertIn("не ответил", r.json()["error"])
            self.assertLess(elapsed, 3, "B не должен ждать дольше таймаута")
        finally:
            stop(orders)
            listener.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
