# Gunicorn configuration
bind = "0.0.0.0:10000"
workers = 1
timeout = 120
accesslog = "-"
errorlog = "-"
capture_output = True


def post_fork(server, worker):
    """Starte Cache-Laden in jedem Worker-Prozess nach dem Fork.

    Falls die App im Master-Prozess vorgeladen wurde (preload_app=True oder
    ähnliche Konfiguration), laufen Hintergrund-Threads nicht im Worker.
    Dieser Hook stellt sicher, dass jeder Worker seinen eigenen Cache lädt.
    """
    import threading
    try:
        import app as flask_app
        cache_thread = getattr(flask_app, '_cache_thread', None)
        if cache_thread is None or not cache_thread.is_alive():
            flask_app._CACHE_LOADING = True
            t = threading.Thread(target=flask_app._background_refresh, daemon=True)
            t.start()
            flask_app._cache_thread = t
    except Exception as e:
        print(f"[post_fork] Fehler beim Starten des Cache-Threads: {e}")
