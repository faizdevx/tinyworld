import asyncio
from datetime import datetime

from tinyworld.core.store import Store
from tinyworld.studio.queue import MAX_ATTEMPTS, JobQueue
from tinyworld.studio.state import Studio
from tinyworld.studio.worker import run_job, work
from tinyworld.eval.studio_bench import scripted


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make(max_running=2):
    clock = Clock()
    store = Store()
    return store, clock, JobQueue(store, now=clock, max_running=max_running)


def world(store, text="a town"):
    return store.create_world(text, datetime(2000, 1, 1, 8))


def test_enqueue_twice_is_one_job():
    store, _, q = make()
    w = world(store)
    q.enqueue(w, "a town")
    q.enqueue(w, "a town")
    assert len(q.all()) == 1


def test_a_job_is_claimed_by_one_worker_only():
    store, _, q = make()
    q.enqueue(world(store), "a town")
    assert q.claim("a") is not None
    assert q.claim("b") is None


def test_the_cap_on_running_builds_holds():
    store, _, q = make(max_running=1)
    q.enqueue(world(store, "x"), "x")
    q.enqueue(world(store, "y"), "y")
    first = q.claim("a")
    assert first and q.claim("b") is None
    q.finish(first.world_id, "a")
    assert q.claim("b") is not None


def test_one_tenant_cannot_starve_another():
    store, clock, q = make(max_running=2)
    for i in range(3):
        clock.t += 1
        q.enqueue(world(store, f"busy {i}"), "busy", tenant="busy")
    clock.t += 1
    other = q.enqueue(world(store, "quiet"), "quiet", tenant="quiet")
    first = q.claim("a")
    second = q.claim("b")
    assert first.tenant == "busy"  # the oldest, nobody running yet
    assert second.world_id == other.world_id  # then the tenant with none running


def test_a_dead_worker_loses_its_job_to_the_next():
    store, clock, q = make()
    job = q.enqueue(world(store), "a town")
    q.claim("dead", lease=30)
    assert q.claim("b") is None
    clock.t += 31
    again = q.claim("b", lease=30)
    assert again.world_id == job.world_id and again.attempts == 2


def test_a_job_that_keeps_killing_workers_fails():
    store, clock, q = make()
    job = q.enqueue(world(store), "a town")
    for _ in range(MAX_ATTEMPTS):
        assert q.claim("w", lease=10)
        clock.t += 11
    assert q.claim("w") is None
    assert q.get(job.world_id).status == "failed"


def test_cancel_takes_the_job_away_from_the_worker():
    store, _, q = make()
    job = q.enqueue(world(store), "a town")
    q.claim("a")
    assert q.cancel(job.world_id)
    assert not q.heartbeat(job.world_id, "a")


def test_position_counts_builds_ahead():
    store, clock, q = make()
    a = q.enqueue(world(store, "a"), "a")
    clock.t += 1
    b = q.enqueue(world(store, "b"), "b")
    assert (q.position(a.world_id), q.position(b.world_id)) == (0, 1)


def test_a_worker_runs_a_build_to_the_end():
    store, _, q = make()
    w = world(store, "A small trading town in the Silk Road, 1250.")
    q.enqueue(w, "A small trading town in the Silk Road, 1250.")
    ran = asyncio.run(work(store, q, scripted, worker="w1", once=True, poll=0.01))
    assert ran == [w]
    assert q.get(w).status == "done"
    studio = Studio(store, w)
    assert studio.graph.finished()


def test_a_worker_resumes_a_build_cut_short():
    store, _, q = make()
    w = world(store, "A small trading town in the Silk Road, 1250.")
    job = q.enqueue(w, "A small trading town in the Silk Road, 1250.")

    async def go():
        # First worker: stop it early, as if the process died.
        claimed = q.claim("w1")
        studio = Studio(store, w)
        llm, search = scripted(store, claimed.payload["goal"])
        from tinyworld.studio.team import Foreman

        foreman = Foreman(studio, llm, search, auto_answer=True)
        foreman.submit(claimed.payload["goal"])
        await asyncio.sleep(0.05)
        await foreman.stop()
        before = len([t for t in studio.graph.all() if t.status == "done"])
        q.store.execute("UPDATE studio_jobs SET lease_until=0 WHERE world_id=?", (w,))
        again = q.claim("w2")
        assert again and again.world_id == job.world_id
        result = await run_job(store, q, again, "w2", scripted)
        return before, result

    before, result = asyncio.run(go())
    assert result == "done"
    after = Studio(store, w)
    assert after.graph.finished()
    assert len([t for t in after.graph.all() if t.status == "done"]) >= before


def test_the_api_queues_a_build_and_lists_it(tmp_path):
    from fastapi.testclient import TestClient

    from tinyworld.api.app import create_app

    client = TestClient(create_app())
    made = client.post("/api/studio/queue?tenant=ann", json={"goal": "A river town, 1700"}).json()
    assert made["position"] == 0
    rows = client.get("/api/studio/queue").json()
    assert rows[0]["world_id"] == made["world_id"] and rows[0]["tenant"] == "ann"
