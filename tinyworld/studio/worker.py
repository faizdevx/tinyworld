"""A worker: takes builds off the queue and runs the team on each.

    python -m tinyworld.studio.worker --db tw.sqlite --enqueue "Lucknow, 1857"
    python -m tinyworld.studio.worker --db tw.sqlite --once        # until the queue is empty
    python -m tinyworld.studio.worker --db tw.sqlite --provider local

Run as many workers as the machine can bear; ``--max-running`` caps them
together. The model comes from the same environment variables as the server
(``--provider local`` with LOCAL_BASE_URL for an open-weight server).
"""

import argparse
import asyncio
import os
import uuid
from datetime import datetime

from tinyworld.core.store import Store
from tinyworld.studio.queue import Job, JobQueue
from tinyworld.studio.replay import RecordingSearch
from tinyworld.studio.state import Studio
from tinyworld.studio.team import Foreman


async def run_job(store: Store, queue: JobQueue, job: Job, worker: str, make_llm_and_search,
                  *, lease: float = 60.0, beat: float | None = None) -> str:
    """Run one claimed job to the end. Returns done, failed or lost."""
    studio = Studio(store, job.world_id)
    goal = job.payload["goal"]
    llm, search = make_llm_and_search(store, goal)
    search = RecordingSearch(search, store, job.world_id)
    foreman = Foreman(studio, llm, search, auto_answer=bool(job.payload.get("auto", True)), max_parallel=3)
    status = studio.data.goal.status if studio.data.goal else None
    if status in ("planning", "running", "paused") and not studio.graph.finished():
        foreman.start()  # a build cut short carries on from its saved state
    elif status is None:
        foreman.submit(goal, budget=job.payload.get("budget"))
    lost = False

    async def keep() -> None:
        nonlocal lost
        while True:
            await asyncio.sleep(beat if beat is not None else lease / 3)
            if not queue.heartbeat(job.world_id, worker, lease=lease):
                lost = True
                await foreman.stop()
                return

    beating = asyncio.create_task(keep())
    try:
        await foreman.wait()
    except Exception as exc:  # noqa: BLE001 - the queue records why
        queue.finish(job.world_id, worker, error=repr(exc))
        return "failed"
    finally:
        beating.cancel()
    if lost:
        return "lost"
    queue.finish(job.world_id, worker)
    return "done"


async def work(store: Store, queue: JobQueue, make_llm_and_search, *, worker: str | None = None,
               once: bool = False, poll: float = 2.0, lease: float = 60.0) -> list[str]:
    """Claim and run jobs. With ``once``, stop when nothing is waiting or running."""
    worker = worker or f"worker-{uuid.uuid4().hex[:6]}"
    ran: list[str] = []
    while True:
        job = queue.claim(worker, lease=lease)
        if job is None:
            if once and not queue.all("queued") and not queue.all("running"):
                return ran
            await asyncio.sleep(poll)
            continue
        await run_job(store, queue, job, worker, make_llm_and_search, lease=lease)
        ran.append(job.world_id)


def make_provider(provider: str):
    """A factory of (llm, search) for a provider name; ``sim`` is the scripted team."""
    if provider == "sim":
        from tinyworld.eval.studio_bench import scripted

        return scripted
    from tinyworld.api.hub import default_search, make_client
    from tinyworld.llm.router import LLMConfig
    from tinyworld.llm.structured import StructuredLLM
    from tinyworld.llm.trace import Tracer

    client = make_client(provider)
    if client is None:
        raise SystemExit(f"Could not create a {provider} client. Is its key set?")

    def real(store, premise):
        config = LLMConfig.load(provider=provider)
        return StructuredLLM(client, config, Tracer(store, config)), default_search(True)

    return real


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=os.environ.get("TINYWORLD_DB", "tinyworld.sqlite"))
    parser.add_argument("--provider", default="sim", choices=["sim", "anthropic", "openrouter", "gemini", "local"])
    parser.add_argument("--max-running", type=int, default=2)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--enqueue", metavar="GOAL")
    parser.add_argument("--tenant", default="default")
    options = parser.parse_args()
    store = Store(options.db)
    queue = JobQueue(store, max_running=options.max_running)
    if options.enqueue:
        world = store.create_world(options.enqueue, datetime(2000, 1, 1, 8))
        queue.enqueue(world, options.enqueue, tenant=options.tenant)
        print(world)
        return
    asyncio.run(work(store, queue, make_provider(options.provider), once=options.once))


if __name__ == "__main__":
    main()
