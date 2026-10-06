"""Um loop de trabalho; a GUI recebe apenas sinais e nunca faz rede ou áudio."""

import asyncio
import threading
import time


class Tasks:
    def __init__(self, emit):
        self.loop = asyncio.new_event_loop()
        self.emit = emit
        self.generation = 0
        self.lock = threading.Lock()
        self.pending_or_running = False
        self.proactive_running = False
        self.job = None
        self.stop_recording = threading.Event()
        self.editing = threading.Event()
        self.engine = None
        self.thread = threading.Thread(target=self._run, name="companhia-worker", daemon=True)
        self.thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.scheduler = self.loop.create_task(self._schedule())
        self.loop.run_forever()
        self.loop.close()

    def current(self, generation):
        with self.lock:
            return generation == self.generation

    def start(self, action, proactive=False):
        with self.lock:
            if proactive and self.pending_or_running:
                return None
            self.generation += 1
            generation = self.generation
            self.pending_or_running = action is not None
            self.proactive_running = proactive
        asyncio.run_coroutine_threadsafe(self._replace(generation, action), self.loop)
        return generation

    def is_proactive(self):
        with self.lock:
            return self.pending_or_running and self.proactive_running

    async def _replace(self, generation, action):
        old = self.job
        if old and not old.done():
            old.cancel()
            await asyncio.gather(old, return_exceptions=True)
        if self.current(generation):
            self.stop_recording = threading.Event()
            self.job = self.loop.create_task(self._execute(generation, action)) if action else None
            self.emit({"generation": generation, "kind": "refresh"})

    async def _execute(self, generation, action):
        try:
            await action(generation)
        except asyncio.CancelledError:
            raise
        except Exception:
            if self.current(generation):
                self.emit(
                    {
                        "generation": generation,
                        "kind": "error",
                        "message": "Falha na tarefa local. Confira dispositivos e configurações.",
                    }
                )
                self.emit({"generation": generation, "kind": "state", "value": "disponível"})
        finally:
            with self.lock:
                if generation == self.generation:
                    self.pending_or_running = False

    def interrupt(self):
        return self.start(None)

    def mode(self, value):
        def change():
            self.engine.proactivity.mode = value
            self.engine.proactivity.last_activity = time.monotonic()

        self.loop.call_soon_threadsafe(change)

    async def _schedule(self):
        while True:
            await asyncio.sleep(1)
            engine = self.engine
            if not engine:
                continue
            has_context = bool(engine.store.recent(1, for_context=True) or engine.store.memories())
            with self.lock:
                busy = self.pending_or_running
            if engine.proactivity.eligible(
                time.monotonic(),
                busy or (self.job is not None and not self.job.done()),
                self.editing.is_set(),
                has_context,
            ):
                self.start(
                    lambda generation, engine=engine: engine.turn(
                        generation, proactive=True, editing=self.editing.is_set
                    ),
                    proactive=True,
                )

    async def _shutdown(self):
        with self.lock:
            self.generation += 1
        self.scheduler.cancel()
        if self.job:
            self.job.cancel()
        await asyncio.gather(self.scheduler, *([self.job] if self.job else []), return_exceptions=True)

    def shutdown(self):
        future = asyncio.run_coroutine_threadsafe(self._shutdown(), self.loop)
        future.result(timeout=10)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
