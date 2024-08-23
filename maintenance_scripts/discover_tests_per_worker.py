# pylint: disable=protected-access
import math
import random
import sys
from typing import Final
from unittest import TestLoader

RANDOM_SEED: Final = 123


def get_chunks(total: int, num_workers: int) -> list[int]:
    base_amount = int(total / num_workers)
    remaining = total - base_amount * num_workers
    remaining_per_worker = math.ceil(remaining / num_workers)

    num_workers_to_add_remaning = leftover = 0
    if remaining_per_worker:
        num_workers_to_add_remaning = remaining // remaining_per_worker
        leftover = remaining % remaining_per_worker

    result = [base_amount] * num_workers
    for i in range(num_workers_to_add_remaning):
        result[i] += remaining_per_worker
    result[num_workers_to_add_remaning] += leftover
    return result


def do_stuff(num_workers: int, worker_idx: int) -> None:
    if worker_idx >= num_workers:
        raise RuntimeError
    tests = [
        test.id()
        for suite in TestLoader().discover(".", "test*.py", ".")._tests  # noqa: SLF001
        for testcase in suite._tests  # type: ignore[attr-defined]  # noqa: SLF001
        for test in testcase._tests  # noqa: SLF001
        if testcase._tests  # noqa: SLF001
    ]
    random.seed(RANDOM_SEED)
    random.shuffle(tests)
    per_worker = get_chunks(len(tests), num_workers)[worker_idx]
    tests_start_idx = worker_idx * per_worker
    tests_end_idx = min(len(tests), tests_start_idx + per_worker)

    # print()
    # print(f"{worker_idx=} from {num_workers=}")
    # print(f"{len(tests)=} tests {per_worker=}")
    # print(f"{tests_start_idx=} : {tests_end_idx=}")
    print("\n".join(tests[tests_start_idx:tests_end_idx]))


if __name__ == "__main__":
    # NUM_WORKERS = 4
    # WORKER_IDX = 2  # starting from 0

    # do_stuff(worker_idx=WORKER_IDX, num_workers=NUM_WORKERS)
    # do_stuff(worker_idx=2, num_workers=3)
    # do_stuff(worker_idx=0, num_workers=5)
    # do_stuff(worker_idx=2, num_workers=7)
    do_stuff(worker_idx=int(sys.argv[1]), num_workers=int(sys.argv[2]))
