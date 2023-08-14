from threading import Lock


class FancyLock:

    _fancy_lock: "Lock | None" = None

    @classmethod
    def get_lock(cls) -> Lock:
        if not cls._fancy_lock:
            cls._fancy_lock = Lock()
        return cls._fancy_lock

    @property
    def fancy_lock(self) -> Lock:
        return self.get_lock()

    def __enter__(self) -> None:
        self.fancy_lock.acquire()

    def __exit__(self, *_exc_details: object) -> None:
        if self.fancy_lock.locked():
            self.fancy_lock.release()

    def __del__(self) -> None:
        self.__exit__()
