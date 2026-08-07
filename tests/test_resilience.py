'''Telegram connectivity: network settings, heartbeat file, connection watchdog.'''

import asyncio
import contextlib
import json

import pytest
from pydantic import ValidationError
from telegram.error import InvalidToken

from sirchatalot import app as app_module
from sirchatalot.app import ConnectionWatchdog, build_application
from sirchatalot.config import TelegramConfig, TelegramNetworkConfig
from sirchatalot.health import check_heartbeat, write_heartbeat
from tests.conftest import make_config


def test_network_defaults_are_proxy_friendly():
    net = make_config().telegram.network
    # PTB's own defaults (5s timeouts, pool_timeout=1, one getUpdates connection)
    # are what produced the TimedOut/PoolTimeout storms behind a proxy
    assert net.connect_timeout >= 20 and net.read_timeout >= 30
    assert net.pool_timeout >= 10
    assert net.get_updates_pool_size > 1
    assert net.watchdog_seconds >= net.heartbeat_seconds


def test_network_settings_are_overridable():
    cfg = make_config(telegram={'token': 't', 'network': {'read_timeout': 45,
                                                          'watchdog_seconds': 0}})
    assert cfg.telegram.network.read_timeout == 45
    assert cfg.telegram.network.watchdog_seconds == 0  # 0 disables the watchdog


def test_watchdog_below_heartbeat_is_rejected():
    with pytest.raises(ValidationError, match='watchdog_seconds'):
        TelegramConfig(token='t', network={'heartbeat_seconds': 60,
                                           'watchdog_seconds': 30})


def test_unknown_network_key_is_rejected():
    with pytest.raises(ValidationError):
        TelegramConfig(token='t', network={'timeout': 5})


# ---- heartbeat file ----

def test_heartbeat_roundtrip(tmp_path):
    path = str(tmp_path / 'sub' / 'heartbeat')  # directory is created on demand
    write_heartbeat(path, ok=True, last_ok=1000.0, now=1000.0)
    assert json.loads(open(path, encoding='utf-8').read())['ok'] is True
    assert check_heartbeat(path, max_age=300, now=1100.0)[0] == 0


def test_heartbeat_missing_or_corrupt(tmp_path):
    path = str(tmp_path / 'heartbeat')
    code, message = check_heartbeat(path, max_age=300)
    assert code == 1 and 'no usable heartbeat' in message
    open(path, 'w', encoding='utf-8').write('{not json')
    assert check_heartbeat(path, max_age=300)[0] == 1


def test_heartbeat_stale_means_unhealthy(tmp_path):
    path = str(tmp_path / 'heartbeat')
    write_heartbeat(path, ok=True, last_ok=1000.0, now=1000.0)
    code, message = check_heartbeat(path, max_age=300, now=1400.0)
    assert code == 1 and 'stale' in message


def test_heartbeat_unhealthy_while_api_unreachable(tmp_path):
    '''The loop keeps ticking (fresh ts) but nothing gets through to Telegram.'''
    path = str(tmp_path / 'heartbeat')
    write_heartbeat(path, ok=False, last_ok=1000.0, now=1600.0)
    code, message = check_heartbeat(path, max_age=300, now=1600.0)
    assert code == 1 and 'unreachable' in message


# ---- watchdog ----

class FakeBot:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    async def get_me(self):
        self.calls += 1
        ok = self.results.pop(0) if self.results else True
        if not ok:
            raise TimeoutError('Timed out')
        return 'me'


class FakeApplication:
    def __init__(self, results):
        self.bot = FakeBot(results)
        self.stopped = False

    def stop_running(self):
        self.stopped = True


def fast_network(**overrides):
    '''A watchdog that gives up after a single failed probe.'''
    return TelegramNetworkConfig(heartbeat_seconds=0.001, watchdog_seconds=0.001,
                                 **overrides)


async def let_it_tick(watchdog, seconds=0.1):
    with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
        await asyncio.wait_for(asyncio.shield(watchdog._task), timeout=seconds)


async def test_watchdog_reconnects_after_failed_probes(tmp_path):
    path = str(tmp_path / 'heartbeat')
    application = FakeApplication([False, False])
    watchdog = ConnectionWatchdog(fast_network(), path=path)
    watchdog.start(application)
    await let_it_tick(watchdog, seconds=2)
    await watchdog.stop()
    assert application.stopped and watchdog.restart_requested
    assert json.loads(open(path, encoding='utf-8').read())['ok'] is False


async def test_watchdog_keeps_polling_while_the_api_answers(tmp_path):
    path = str(tmp_path / 'heartbeat')
    application = FakeApplication([True] * 20)
    watchdog = ConnectionWatchdog(fast_network(), path=path)
    watchdog.start(application)
    await let_it_tick(watchdog)
    await watchdog.stop()
    assert not application.stopped and not watchdog.restart_requested
    assert application.bot.calls > 0
    assert check_heartbeat(path, max_age=300)[0] == 0


async def test_watchdog_disabled_never_stops_the_application(tmp_path):
    path = str(tmp_path / 'heartbeat')
    net = TelegramNetworkConfig(heartbeat_seconds=0.001, watchdog_seconds=0)
    application = FakeApplication([False] * 100)
    watchdog = ConnectionWatchdog(net, path=path)
    watchdog.start(application)
    await let_it_tick(watchdog)
    await watchdog.stop()
    assert application.bot.calls > 0
    assert not application.stopped and not watchdog.restart_requested


# ---- application wiring ----

def test_build_application_applies_network_settings(db):
    cfg = make_config(telegram={'token': '123456:test-token',
                                'network': {'get_updates_pool_size': 4,
                                            'read_timeout': 42}},
                      proxies={'telegram': 'http://proxy:3128'})
    application = build_application(cfg, db, ConnectionWatchdog(cfg.telegram.network))
    request = application.bot.request
    get_updates_request = application.bot._request[0]
    assert request.read_timeout == 42
    assert get_updates_request.read_timeout == 42
    assert get_updates_request._client_kwargs['limits'].max_connections == 4
    assert str(request._client_kwargs['proxy']) == 'http://proxy:3128'
    assert str(get_updates_request._client_kwargs['proxy']) == 'http://proxy:3128'


async def test_post_init_starts_and_post_shutdown_stops_the_watchdog(db, tmp_path):
    cfg = make_config(telegram={'token': '123456:test-token'})
    watchdog = ConnectionWatchdog(cfg.telegram.network, path=str(tmp_path / 'heartbeat'))
    application = build_application(cfg, db, watchdog)

    await application.post_init(application)
    assert watchdog._task is not None and not watchdog._task.done()
    assert check_heartbeat(watchdog.path, max_age=300)[0] == 0
    assert application.bot_data['services'] is not None

    await application.post_shutdown(application)
    assert watchdog._task is None


# ---- supervisor loop ----

class StubApplication:
    '''Stands in for a built Application: run_polling replays a scripted outcome.'''

    def __init__(self, outcome):
        self.outcome = outcome

    def run_polling(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome


def run_with_outcomes(monkeypatch, outcomes, watchdog_restarts=()):
    '''Drive run() over a scripted sequence of run_polling outcomes.'''
    built = []
    restarts = list(watchdog_restarts)

    def fake_build(cfg, db, watchdog):
        watchdog.restart_requested = restarts.pop(0) if restarts else False
        application = StubApplication(outcomes[len(built)])
        built.append(application)
        return application

    monkeypatch.setattr(app_module, 'build_application', fake_build)
    monkeypatch.setattr(app_module, 'load_config', lambda *a, **kw: make_config())
    monkeypatch.setattr(app_module.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(app_module, 'setup_logging', lambda level: None)
    app_module.run()
    return built


def test_run_restarts_polling_after_a_crash(monkeypatch):
    built = run_with_outcomes(monkeypatch, [RuntimeError('boom'), None])
    assert len(built) == 2  # crashed once, then ran and stopped cleanly
    assert built[0].kwargs['bootstrap_retries'] == -1  # wait for Telegram at startup


def test_run_reconnects_when_the_watchdog_asks(monkeypatch):
    built = run_with_outcomes(monkeypatch, [None, None],
                              watchdog_restarts=[True, False])
    assert len(built) == 2


def test_run_stops_on_a_clean_shutdown(monkeypatch):
    assert len(run_with_outcomes(monkeypatch, [None])) == 1


def test_run_exits_on_an_invalid_token(monkeypatch):
    with pytest.raises(SystemExit):
        run_with_outcomes(monkeypatch, [InvalidToken('nope')])
