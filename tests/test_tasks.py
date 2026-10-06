import asyncio
import threading

from companhia.tasks import Tasks


def test_pending_user_action_cannot_be_replaced_by_scheduler():
    tasks = Tasks(lambda event: None)
    began = threading.Event()

    async def user(generation):
        began.set()
        await asyncio.Event().wait()

    try:
        generation = tasks.start(user)
        # A reserva existe antes de o loop iniciar a tarefa: fecha a corrida com o agendador.
        assert tasks.start(lambda g: asyncio.sleep(0), proactive=True) is None
        assert tasks.current(generation)
        assert began.wait(2)
        assert tasks.start(lambda g: asyncio.sleep(0), proactive=True) is None
        next_generation = tasks.interrupt()
        assert next_generation > generation
        assert not tasks.current(generation)
    finally:
        tasks.shutdown()
