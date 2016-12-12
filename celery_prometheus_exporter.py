import argparse
import celery
import celery.states
import collections
import logging
import prometheus_client
import signal
import sys
import os
import threading
import time
import random

__VERSION__ = (2, 0, 0, 'final', 0)


DEFAULT_BROKER = 'redis://redis:6379/0'
DEFAULT_ADDR = '0.0.0.0:9000'

LOG_FORMAT = '[%(asctime)s] %(name)s:%(levelname)s: %(message)s'

TASKS = prometheus_client.Counter('celery_tasks', 'Number of tasks per state', ['state', "worker", "task_name", "routing_key"])
WORKERS = prometheus_client.Gauge('celery_workers', 'Number of alive workers')

UPTIME = None

def check_worker_general_failure(worker_pool_size):
    if worker_pool_size is 0:
        global UPTIME
        if UPTIME is None:
            UPTIME = prometheus_client.Gauge('celery_last_failure_time', 'Timestamp of the last failure, to compute uptime')
        UPTIME.set(int(round(time.time() * 1000)))

class MonitorThread(threading.Thread):
    """
    MonitorThread is the thread that will collect the data that is later
    exposed from Celery using its eventing system.
    """

    def __init__(self, *args, app=None, **kwargs):
        self._app = app
        self.log = logging.getLogger('monitor')
        super().__init__(*args, **kwargs)

    def run(self):
        self._state = self._app.events.State(
            max_workers_in_memory=42,
            max_tasks_in_memory=10000
        )
        self._monitor()

    def _process_event(self, event):
        # Events might come in in parallel. Celery already has a lock that deals
        # with this exact situation so we'll use that for now.
        with self._state._mutex:
            self._state._event(event)
            if event['type'].find("task") is not -1:
                task = self._state.tasks.get(event['uuid'])
#                self.log.info((task.state, task.uuid, task.args))
                TASKS.labels(
                    state=task.state,
                    worker=task.worker.hostname,
                    task_name=task.name,
                    routing_key=task.routing_key
                ).inc(1)
            elif event['type'].find("worker") is not -1:
                worker_pool_size = len([w for w in self._state.workers.values() if w.alive])
                WORKERS.set(worker_pool_size)
                check_worker_general_failure(worker_pool_size)
            else:
                self.log.info("Unknown event type: " + event['type'])

    def _monitor(self):
        while True:
            try:
                with self._app.connection() as conn:
                    recv = self._app.events.Receiver(conn, handlers={
                        '*': self._process_event,
                    })
                    recv.capture(limit=None, timeout=None, wakeup=True)
                    self.log.info("Connected to broker")
            except Exception as e:
                self.log.error("Queue connection failed", e)
                time.sleep(5)


# override the prometheus_client handler to ping workers
# this is needed because if every producers, workers and celerybeat die, _process_event could never be called
class CustomMetricsHandler(prometheus_client.MetricsHandler):
    def __init__(self, *args, **kwargs):
        self._app = celery.Celery(broker=DEFAULT_BROKER)
        super(CustomMetricsHandler, self).__init__(*args, **kwargs)

    def do_GET(self):
        super(CustomMetricsHandler, self).do_GET()
        # pinging workers can take some time
        # so we won't do it at each scrape
        # we ping workers after metric collection because prometheus store the timestamp of the request beginning
        if random.randint(0, 10) is 0:
            workers = self._app.control.ping(timeout=1)
            WORKERS.set(len(workers))
            check_worker_general_failure(len(workers))

def start_httpd(addr):
    """
    Starts the exposing HTTPD using the addr provided in a seperate
    thread.
    """
    host, port = addr.split(':')
    logging.info('Starting HTTPD on {}:{}'.format(host, port))

    class PrometheusMetricsServer(threading.Thread):
        def run(self):
            from http.server import HTTPServer
            httpd = HTTPServer((host, int(port)), CustomMetricsHandler)
            httpd.serve_forever()
    t = PrometheusMetricsServer()
    t.daemon = True
    t.start()
#    prometheus_client.start_http_server(int(port), host)


def shutdown(signum, frame):
    """
    Shutdown is called if the process receives a TERM signal. This way
    we try to prevent an ugly stacktrace being rendered to the user on
    a normal shutdown.
    """
    logging.info("Shutting down")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--broker', dest='broker', default=DEFAULT_BROKER,
        help="URL to the Celery broker. Defaults to {}".format(DEFAULT_BROKER))
    parser.add_argument(
        '--addr', dest='addr', default=DEFAULT_ADDR,
        help="Address the HTTPD should listen on. Defaults to {}".format(
            DEFAULT_ADDR))
    parser.add_argument(
        '--verbose', action='store_true', default=False,
        help="Enable verbose logging")
    parser.add_argument(
        '--version', action='version', version='.'.join([str(x) for x in __VERSION__]))
    opts = parser.parse_args()

    if opts.verbose:
        logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)
    else:
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    global DEFAULT_BROKER
    DEFAULT_BROKER = opts.broker
    t = MonitorThread(app=celery.Celery(broker=opts.broker))
    t.daemon = True
    t.start()
    start_httpd(opts.addr)
    t.join()


if __name__ == '__main__':
    main()
