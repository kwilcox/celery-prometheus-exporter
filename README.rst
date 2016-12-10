==========================
celery-prometheus-exporter
==========================

celery-prometheus-exporter is a little exporter for Celery related metrics in
order to get picked up by Prometheus. As with other exporters like
mongodb\_exporter or node\_exporter this has been implemented as a
standalone-service to make reuse easier across different frameworks.

So far it provides access to the following metrics:

* ``celery_tasks`` exposes the number of tasks currently known to the queue
  seperated by ``state`` (RUNNING, STARTED, ...), ``task_name``, ``routing_key`` and ``worker`` id.
* ``celery_workers`` exposes the number of currently probably alive workers

Why did I forked it ?
=====================

This is a fork of https://github.com/zerok/celery-prometheus-exporter.
Unfortunately, it requested major changes, that would break any previous metric export.

* HTTP server listen on port 9000 by default (generic port for prometheus exporters).
* The cache size of the ``_state`` attribute in ``MonitorThread`` was limited to 10.000. This may be increased with ``self._app.events.State(max_tasks_in_memory=xxxxx)``. But it's actually not the point, since it was also limiting the metric to 10.000.
* ``celery_tasks`` metrics is no longer a gauge: counter are more convienent for metrics keep increasing to inf+

How to use
==========

::

   $ docker run --rm -it --name celery-exporter -p 9000:9000 -e EXPORTER_PORT=9000 samber/celery-exporter

If you want the HTTPD to listen to another port, use the ``--addr`` option.

By default, this will expect the broker to be available through
``redis://redis:6379/0``. If you're using AMQP or something else other than
Redis, take a look at the Celery documentation and install the additioinal
requirements 😊 Also use the ``--broker`` option to specify a different broker
URL.

If you then look at the exposed metrics, you should see something like this::

  $ http get http://localhost:9000/metrics | grep celery_
  # HELP celery_workers Number of alive workers
  # TYPE celery_workers gauge
  celery_workers 1.0
  # HELP celery_tasks Number of tasks per state
  # TYPE celery_tasks count
  celery_tasks{state="PENDING", routing_key=None, worker="celery1@684dbcb0-9480-47b1-ac43-feb1eba252ac", task_name="grep.tasks.check_update"} 1.0
  celery_tasks{state="STARTED", routing_key=None, worker="celery1@684dbcb0-9480-47b1-ac43-feb1eba252ac", task_name="grep.tasks.check_update"} 0.0
  celery_tasks{state="SUCCESS", routing_key=None, worker="celery1@684dbcb0-9480-47b1-ac43-feb1eba252ac", task_name="grep.tasks.check_update"} 42.0
  celery_tasks{state="FAILURE", routing_key=None, worker="celery1@684dbcb0-9480-47b1-ac43-feb1eba252ac", task_name="grep.tasks.check_update"} 0.0
  celery_tasks{state="RECEIVED", routing_key=None, worker="celery1@684dbcb0-9480-47b1-ac43-feb1eba252ac", task_name="grep.tasks.check_update"} 0.0
  celery_tasks{state="REVOKED", routing_key=None, worker="celery1@684dbcb0-9480-47b1-ac43-feb1eba252ac", task_name="grep.tasks.check_update"} 0.0
  celery_tasks{state="RETRY", routing_key=None, worker="celery1@684dbcb0-9480-47b1-ac43-feb1eba252ac", task_name="grep.tasks.check_update"} 0.0

Limitations
===========

* This has only been tested with Redis so far.
