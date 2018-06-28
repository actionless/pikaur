import traceback
import uuid
from threading import Lock
from typing import List, Callable, Any, Dict

from .pprint import print_stderr


class ThreadSafeSequentialStorage():

    _storage: Dict[uuid.UUID, Any] = {}
    _locks: Dict[uuid.UUID, Lock] = {}

    @classmethod
    def _check_lock_and_storage(cls, _id) -> None:
        if _id not in cls._storage:
            cls._storage[_id] = []
            cls._locks[_id] = Lock()

    @classmethod
    def _get_storage(cls, _id: uuid.UUID) -> List:
        cls._check_lock_and_storage(_id)
        return cls._storage[_id]

    @classmethod
    def _get_lock(cls, _id: uuid.UUID) -> Lock:
        cls._check_lock_and_storage(_id)
        return cls._locks[_id]

    @classmethod
    def _add_item(cls, _id: uuid.UUID, item: Any) -> None:
        lock = cls._get_lock(_id)
        lock.acquire()
        cls._get_storage(_id).append(item)
        lock.release()


class ThreadSafeBytesStorage(ThreadSafeSequentialStorage):

    @classmethod
    def add_bytes(cls, _id: uuid.UUID, chars: bytes) -> None:
        super()._add_item(_id, chars)

    @classmethod
    def get_bytes_output(cls, _id: uuid.UUID) -> bytes:
        return b''.join(cls._get_storage(_id))


def handle_exception_in_thread(fun: Callable) -> Callable:

    def decorated(*args: Any, **kwargs: Any):
        try:
            return fun(*args, **kwargs)
        # except OSError:
        # pass
        except Exception as exc:
            print_stderr('Error in the thread:')
            traceback.print_exc()
            raise exc

    return decorated
