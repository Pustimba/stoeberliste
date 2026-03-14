# Gunicorn configuration
bind = "0.0.0.0:10000"
workers = 1
timeout = 120
accesslog = "-"
errorlog = "-"
capture_output = True
import os


def post_fork(server, worker):
    """Starte Cache-Laden in jedem Worker-Prozess nach dem Fork.

    Falls die App im Master-Prozess vorgeladen wurde (preload_app=True oder
    ähnliche Konfiguration), laufen Hintergrund-Threads nicht im Worker.
    Dieser Hook stellt sicher, dass jeder Worker seinen eigenen Cache lädt
    und der Auto-Refresh (z.B. via threading.Timer in _schedule_refresh)
    in jedem Worker neu geplant wird.
    """
    import threading
    try:
        import app as flask_app

        # Cache-Thread im Worker sicherstellen
        cache_thread = getattr(flask_app, '_cache_thread', None)
        if cache_thread is None or not cache_thread.is_alive():
            flask_app._CACHE_LOADING = True
            t = threading.Thread(target=flask_app._background_refresh, daemon=True)
            t.start()
            flask_app._cache_thread = t

        # Auto-Refresh (z.B. durch _schedule_refresh mit threading.Timer)
        # pro Prozess genau einmal planen. Die PID ändert sich nach dem Fork,
        # wodurch Worker ihren eigenen Timer erhalten.
        schedule_refresh = getattr(flask_app, '_schedule_refresh', None)
        if callable(schedule_refresh):
            current_pid = os.getpid()
            last_pid = getattr(flask_app, '_AUTO_REFRESH_PID', None)
            if last_pid != current_pid:
                try:
                    schedule_refresh()
                    flask_app._AUTO_REFRESH_PID = current_pid
                except Exception as e_inner:
                    print(f"[post_fork] Fehler beim Planen des Auto-Refresh: {e_inner}")
    except Exception as e:
        print(f"[post_fork] Fehler beim Starten des Cache-Threads: {e}")
