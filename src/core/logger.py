from datetime import datetime


class Logger:

    def _log(self, level: str, message: str, prefix: str | None = None):
        now = datetime.now().strftime("%H:%M:%S")
        if prefix:
            print(f"[{now}] [{level}] [{prefix}] {message}")
        else:
            print(f"[{now}] [{level}] {message}")

    def info(self, message: str):
        self._log("INFO", message)

    def success(self, message: str):
        self._log("SUCCESS", message)

    def warning(self, message: str):
        self._log("WARNING", message)

    def error(self, message: str):
        self._log("ERROR", message)

    def provider(self, provider: str, message: str):
        self._log("PROVIDER", message, prefix=provider)

    def router(self, message: str):
        self._log("ROUTER", message)


logger = Logger()