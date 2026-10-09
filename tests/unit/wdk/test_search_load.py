from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

import httpx
import pytest

from veupathdb.observer import MetricAttrs, get_observer, set_observer
from veupathdb.wdk import (
    HIGH_SPEED_SNP_SEARCHES,
    SearchRequest,
    VEuPathDBClient,
    WDKSearchConfig,
    WDKStep,
    WDKStepTree,
    WDKStrategyDetails,
    runs_an_expensive_search,
    search_gate,
    search_turn,
    use_search_gate,
)

_SNP_REPORT = "/record-types/transcript/searches/GenesByNgsSnps/reports/standard"


class _Load:
    def __init__(self) -> None:
        self.in_flight = 0
        self.most_in_flight = 0

    def enter(self) -> None:
        self.in_flight += 1
        self.most_in_flight = max(self.most_in_flight, self.in_flight)


class _Site(httpx.AsyncBaseTransport):
    def __init__(self, load: _Load | None = None) -> None:
        self.load = load or _Load()
        self.in_flight = 0
        self.most_in_flight = 0
        self.sent: list[str] = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()
        self.next_id = 100

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/app"):
            return httpx.Response(200, text="ok")
        self.sent.append(request.url.path)
        self.in_flight += 1
        self.most_in_flight = max(self.most_in_flight, self.in_flight)
        self.load.enter()
        self.entered.set()
        for _ in range(5):
            await asyncio.sleep(0)
        await self.release.wait()
        self.in_flight -= 1
        self.load.in_flight -= 1
        self.next_id += 1
        return httpx.Response(200, json={"id": self.next_id})


class _ClockedSite(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/app"):
            return httpx.Response(200, text="ok")
        budget = request.extensions["timeout"]["read"]
        try:
            async with asyncio.timeout(budget):
                await asyncio.sleep(0.05)
        except TimeoutError as exc:
            msg = "read timed out"
            raise httpx.ReadTimeout(msg, request=request) from exc
        return httpx.Response(200, json={"id": 1})


class _Waits:
    def __init__(self) -> None:
        self.waits: list[tuple[float, MetricAttrs]] = []

    def on_wdk_request(self, _seconds: float, _attrs: MetricAttrs, /) -> None:
        return None

    def on_wdk_retry(self, _attrs: MetricAttrs, /) -> None:
        return None

    def on_site_search_request(self, _seconds: float, _attrs: MetricAttrs, /) -> None:
        return None

    def on_site_search_retry(self, _attrs: MetricAttrs, /) -> None:
        return None

    def on_wdk_search_wait(self, seconds: float, attrs: MetricAttrs, /) -> None:
        self.waits.append((seconds, attrs))


async def _client(
    transport: httpx.AsyncBaseTransport,
    *,
    site_id: str = "plasmodb",
    concurrent_searches: int = 4,
    seconds: float = 30.0,
) -> VEuPathDBClient:
    client = VEuPathDBClient(
        base_url=f"https://{site_id}.invalid/service",
        site_id=site_id,
        concurrent_searches=concurrent_searches,
        timeout=seconds,
    )
    async with client._client_lock:
        client._client = httpx.AsyncClient(
            base_url=client.base_url,
            transport=transport,
            follow_redirects=True,
            timeout=httpx.Timeout(seconds),
        )
    return client


def _report(client: VEuPathDBClient, step: int) -> asyncio.Task[object]:
    return asyncio.create_task(
        client.post(f"/users/1/steps/{step}/reports/standard", json={})
    )


@pytest.fixture
def gate_calls() -> Iterator[list[SearchRequest]]:
    calls: list[SearchRequest] = []
    previous = search_gate()

    @asynccontextmanager
    async def recording(request: SearchRequest) -> AsyncIterator[None]:
        calls.append(request)
        yield

    use_search_gate(recording)
    try:
        yield calls
    finally:
        use_search_gate(previous)


@pytest.fixture
def waits() -> Iterator[_Waits]:
    recording = _Waits()
    previous = get_observer()
    set_observer(recording)
    try:
        yield recording
    finally:
        set_observer(previous)


@pytest.mark.usefixtures("wdk_request_token")
class TestOneTurnRunsOneSearchPerSite:
    async def test_two_searches_of_one_turn_run_one_after_the_other(self) -> None:
        site = _Site()
        client = await _client(site)

        with search_turn():
            await asyncio.gather(_report(client, 1), _report(client, 2))

        assert site.most_in_flight == 1
        assert len(site.sent) == 2

    async def test_a_fan_out_inside_a_turn_still_runs_one_at_a_time(self) -> None:
        site = _Site()
        client = await _client(site)
        fan_out = asyncio.Semaphore(5)

        async def counted(step: int) -> object:
            async with fan_out:
                return await client.post(
                    f"/users/1/steps/{step}/reports/standard", json={}
                )

        with search_turn():
            await asyncio.gather(*(counted(step) for step in range(5)))

        assert site.most_in_flight == 1
        assert len(site.sent) == 5

    async def test_two_turns_run_their_searches_side_by_side(self) -> None:
        site = _Site()
        client = await _client(site)

        async def one_turn(step: int) -> object:
            with search_turn():
                return await client.post(
                    f"/users/1/steps/{step}/reports/standard", json={}
                )

        await asyncio.gather(one_turn(1), one_turn(2))

        assert site.most_in_flight == 2

    async def test_one_turn_searches_two_sites_side_by_side(self) -> None:
        both = _Load()
        plasmo_client = await _client(_Site(both), site_id="plasmodb")
        toxo_client = await _client(_Site(both), site_id="toxodb")

        with search_turn():
            await asyncio.gather(_report(plasmo_client, 1), _report(toxo_client, 2))

        assert both.most_in_flight == 2

    async def test_a_metadata_read_of_the_turn_does_not_wait_for_its_search(
        self,
    ) -> None:
        site = _Site()
        site.release.clear()
        client = await _client(site)

        with search_turn():
            held = _report(client, 1)
            await site.entered.wait()
            site.entered.clear()
            read = asyncio.create_task(client.get("/users/1/strategies"))
            await site.entered.wait()
            site.release.set()
            await asyncio.gather(held, read)

        assert site.most_in_flight == 2


@pytest.mark.usefixtures("wdk_request_token")
class TestThePerProcessCapStands:
    async def test_without_a_turn_a_site_runs_as_many_as_its_slots(self) -> None:
        site = _Site()
        client = await _client(site, concurrent_searches=2)

        await asyncio.gather(*(_report(client, step) for step in range(6)))

        assert site.most_in_flight == 2
        assert len(site.sent) == 6

    async def test_many_turns_together_still_share_the_slots(self) -> None:
        site = _Site()
        client = await _client(site, concurrent_searches=2)

        async def one_turn(step: int) -> object:
            with search_turn():
                return await client.post(
                    f"/users/1/steps/{step}/reports/standard", json={}
                )

        await asyncio.gather(*(one_turn(step) for step in range(6)))

        assert site.most_in_flight == 2


@pytest.mark.usefixtures("wdk_request_token")
class TestAWaitIsNotARequest:
    async def test_time_in_line_does_not_count_against_the_request_timeout(
        self,
    ) -> None:
        client = await _client(_ClockedSite(), seconds=0.2)
        previous = search_gate()

        @asynccontextmanager
        async def slow_line(_request: SearchRequest) -> AsyncIterator[None]:
            await asyncio.sleep(0.4)
            yield

        use_search_gate(slow_line)
        try:
            answer = await client.post(_SNP_REPORT, json={})
        finally:
            use_search_gate(previous)

        assert answer == {"id": 1}

    async def test_a_cancelled_waiter_leaves_the_line_to_the_next(self) -> None:
        site = _Site()
        site.release.clear()
        client = await _client(site)

        with search_turn():
            held = _report(client, 1)
            await site.entered.wait()
            cancelled = _report(client, 2)
            await asyncio.sleep(0)
            assert not cancelled.done()
            cancelled.cancel()
            with pytest.raises(asyncio.CancelledError):
                await cancelled
            site.release.set()
            await held
            await client.post("/users/1/steps/3/reports/standard", json={})

        assert site.sent == [
            "/service/users/1/steps/1/reports/standard",
            "/service/users/1/steps/3/reports/standard",
        ]

    async def test_a_cancelled_waiter_frees_its_process_slot_place(self) -> None:
        site = _Site()
        site.release.clear()
        client = await _client(site, concurrent_searches=1)

        held = _report(client, 1)
        await site.entered.wait()
        cancelled = _report(client, 2)
        await asyncio.sleep(0)
        assert not cancelled.done()
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        site.release.set()
        await held
        await client.post("/users/1/steps/3/reports/standard", json={})

        assert site.sent == [
            "/service/users/1/steps/1/reports/standard",
            "/service/users/1/steps/3/reports/standard",
        ]

    async def test_the_waits_are_reported_by_line(self, waits: _Waits) -> None:
        site = _Site()
        client = await _client(site)

        with search_turn():
            await asyncio.gather(_report(client, 1), _report(client, 2))

        lines = sorted(attrs["line"] for _, attrs in waits.waits)
        assert lines == ["site", "site", "turn", "turn"]
        assert {attrs["site"] for _, attrs in waits.waits} == {"plasmodb"}


@pytest.mark.usefixtures("wdk_request_token")
class TestTheHostGate:
    async def test_a_search_report_names_its_search(
        self, gate_calls: list[SearchRequest]
    ) -> None:
        client = await _client(_Site())

        await client.post(_SNP_REPORT, json={})

        assert gate_calls == [
            SearchRequest(
                site_id="plasmodb",
                kind="report",
                search_names=frozenset({"GenesByNgsSnps"}),
            )
        ]

    async def test_a_metadata_request_passes_no_gate(
        self, gate_calls: list[SearchRequest]
    ) -> None:
        client = await _client(_Site())

        await client.get("/record-types/transcript/searches/GenesByNgsSnps")

        assert gate_calls == []

    async def test_a_step_this_client_created_is_named_by_its_search(
        self, gate_calls: list[SearchRequest]
    ) -> None:
        site = _Site()
        client = await _client(site)

        created = await client.post(
            "/users/1/steps",
            json={"searchName": "NgsSnpsByLocation", "searchConfig": {}},
            idempotent=False,
        )
        await client.post(f"/users/1/steps/{_id(created)}/reports/standard", json={})
        await client.get(f"/users/1/steps/{_id(created)}")

        assert [(c.kind, c.search_names) for c in gate_calls] == [
            ("step", frozenset({"NgsSnpsByLocation"})),
            ("step", frozenset({"NgsSnpsByLocation"})),
        ]

    async def test_a_strategy_and_its_root_name_every_search_of_the_tree(
        self, gate_calls: list[SearchRequest]
    ) -> None:
        client = await _client(_Site())
        snp = _id(await _new_step(client, "GenesByNgsSnps"))
        text = _id(await _new_step(client, "GenesByText"))
        root = _id(await _new_step(client, "boolean_question_GeneRecordClasses"))
        tree = {
            "stepId": root,
            "primaryInput": {"stepId": snp},
            "secondaryInput": {"stepId": text},
        }
        strategy = _id(
            await client.post(
                "/users/1/strategies",
                json={"name": "s", "stepTree": tree},
                idempotent=False,
            )
        )

        await client.get(f"/users/1/strategies/{strategy}")
        await client.post(f"/users/1/steps/{root}/reports/standard", json={})
        await client.post(
            f"/users/1/steps/{root}/analyses/4/result", json={}, idempotent=False
        )

        everything = frozenset(
            {"GenesByNgsSnps", "GenesByText", "boolean_question_GeneRecordClasses"}
        )
        assert [(c.kind, c.search_names) for c in gate_calls] == [
            ("strategy", everything),
            ("step", everything),
            ("analysis", everything),
        ]

    async def test_a_new_tree_replaces_the_inputs_a_strategy_read_names(
        self, gate_calls: list[SearchRequest]
    ) -> None:
        client = await _client(_Site())
        snp = _id(await _new_step(client, "GenesByNgsSnps"))
        text = _id(await _new_step(client, "GenesByText"))
        strategy = _id(
            await client.post(
                "/users/1/strategies",
                json={"name": "s", "stepTree": {"stepId": snp}},
                idempotent=False,
            )
        )

        await client.put(
            f"/users/1/strategies/{strategy}/step-tree",
            json={"stepTree": {"stepId": text}},
        )
        await client.get(f"/users/1/strategies/{strategy}")

        assert [c.search_names for c in gate_calls] == [frozenset({"GenesByText"})]

    async def test_a_step_no_request_named_passes_the_gate_unnamed(
        self, gate_calls: list[SearchRequest]
    ) -> None:
        client = await _client(_Site())

        await client.post("/users/1/steps/77/reports/standard", json={})

        assert gate_calls == [
            SearchRequest(site_id="plasmodb", kind="step", search_names=frozenset())
        ]

    async def test_a_request_waiting_at_the_gate_holds_no_process_slot(
        self,
    ) -> None:
        site = _Site()
        client = await _client(site, concurrent_searches=1)
        arrived = asyncio.Event()
        opened = asyncio.Event()
        previous = search_gate()

        @asynccontextmanager
        async def closed_for_snps(request: SearchRequest) -> AsyncIterator[None]:
            if runs_an_expensive_search(request):
                arrived.set()
                await opened.wait()
            yield

        use_search_gate(closed_for_snps)
        try:
            waiting = asyncio.create_task(client.post(_SNP_REPORT, json={}))
            await arrived.wait()
            await client.post("/users/1/steps/9/reports/standard", json={})
            assert not waiting.done()
            opened.set()
            await waiting
        finally:
            use_search_gate(previous)

        assert site.sent[0] == "/service/users/1/steps/9/reports/standard"


async def _new_step(client: VEuPathDBClient, search_name: str) -> object:
    return await client.post(
        "/users/1/steps",
        json={"searchName": search_name, "searchConfig": {}},
        idempotent=False,
    )


def _id(answer: object) -> int:
    assert isinstance(answer, dict)
    value = answer["id"]
    assert isinstance(value, int)
    return value


HSSS_SEARCHES = [
    "GenesByNgsSnps",
    "NgsSnpsByGeneIds",
    "NgsSnpsByIsolateGroup",
    "NgsSnpsByLocation",
    "NgsSnpsByTwoIsolateGroups",
    "NgsSnpsByTwoIsolateGroupsWiz",
    "SnpsByGeneId",
    "SnpsByIsolatePattern",
    "SnpsByStrain",
    "VariantsByGeneIds",
    "VariantsByIsolateGroup",
    "VariantsByLocation",
    "VariantsByTwoIsolateGroups",
]
SQL_SEARCHES = [
    "NgsSnpBySourceId",
    "VariantBySourceId",
    "SnpAlignmentForm",
    "GenesByVariantCharacteristics",
    "SnpsByIsolateType",
    "GenesByText",
]


def test_the_list_is_every_high_speed_snp_search() -> None:
    assert sorted(HIGH_SPEED_SNP_SEARCHES) == HSSS_SEARCHES


@pytest.mark.parametrize("name", HSSS_SEARCHES)
def test_a_high_speed_snp_search_is_expensive(name: str) -> None:
    request = SearchRequest(
        site_id="plasmodb", kind="report", search_names=frozenset({name})
    )

    assert runs_an_expensive_search(request) is True


@pytest.mark.parametrize("name", SQL_SEARCHES)
def test_a_search_on_sql_is_not(name: str) -> None:
    request = SearchRequest(
        site_id="plasmodb", kind="report", search_names=frozenset({name})
    )

    assert runs_an_expensive_search(request) is False


def test_a_tree_with_one_snp_step_is_expensive() -> None:
    request = SearchRequest(
        site_id="plasmodb",
        kind="strategy",
        search_names=frozenset({"GenesByText", "VariantsByLocation"}),
    )

    assert runs_an_expensive_search(request) is True


class _Bodies(httpx.AsyncBaseTransport):
    def __init__(self, bodies: dict[str, object]) -> None:
        self.bodies = bodies

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/service")
        return httpx.Response(200, json=self.bodies.get(path, {"id": 1}))


def _step_body(step_id: int, search_name: str) -> dict[str, object]:
    return WDKStep(
        id=step_id,
        search_name=search_name,
        search_config=WDKSearchConfig(parameters={}),
    ).model_dump(by_alias=True, mode="json")


def _strategy_body() -> dict[str, object]:
    return WDKStrategyDetails(
        strategy_id=5,
        name="s",
        root_step_id=30,
        step_tree=WDKStepTree(
            step_id=30,
            primary_input=WDKStepTree(step_id=10),
            secondary_input=WDKStepTree(step_id=20),
        ),
        steps={
            "10": WDKStep.model_validate(_step_body(10, "GenesByNgsSnps")),
            "20": WDKStep.model_validate(_step_body(20, "GenesByText")),
            "30": WDKStep.model_validate(
                _step_body(30, "boolean_question_GeneRecordClasses")
            ),
        },
    ).model_dump(by_alias=True, mode="json")


@pytest.mark.usefixtures("wdk_request_token")
class TestAReadTeachesTheNames:
    async def test_a_strategy_read_names_its_steps_for_every_later_request(
        self, gate_calls: list[SearchRequest]
    ) -> None:
        client = await _client(_Bodies({"/users/1/strategies/5": _strategy_body()}))

        await client.get("/users/1/strategies/5")
        await client.post("/users/1/steps/30/reports/standard", json={})
        await client.get("/users/1/strategies/5")

        everything = frozenset(
            {"GenesByNgsSnps", "GenesByText", "boolean_question_GeneRecordClasses"}
        )
        assert [c.search_names for c in gate_calls] == [
            frozenset(),
            everything,
            everything,
        ]

    async def test_a_step_read_names_its_search(
        self, gate_calls: list[SearchRequest]
    ) -> None:
        client = await _client(
            _Bodies({"/users/1/steps/10": _step_body(10, "VariantsByLocation")})
        )

        await client.get("/users/1/steps/10")
        await client.post("/users/1/steps/10/reports/standard", json={})

        assert [c.search_names for c in gate_calls] == [
            frozenset(),
            frozenset({"VariantsByLocation"}),
        ]


class _Slow(httpx.AsyncBaseTransport):
    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        del request
        await asyncio.sleep(self.seconds)
        return httpx.Response(200, json={"id": 1})


@pytest.mark.usefixtures("wdk_request_token")
class TestABudgetStartsAtTheSend:
    async def test_time_in_line_does_not_count_against_the_budget(self) -> None:
        site = _Site()
        site.release.clear()
        client = await _client(site)

        with search_turn():
            ahead = _report(client, 1)
            await site.entered.wait()
            behind = asyncio.create_task(
                client.post(_SNP_REPORT, json={}, budget_seconds=0.2)
            )
            await asyncio.sleep(0.4)
            site.release.set()
            await ahead
            answer = await behind

        assert answer == {"id": 102}

    async def test_a_request_past_its_budget_after_the_send_ends(self) -> None:
        client = await _client(_Slow(0.5))

        with pytest.raises(TimeoutError):
            await client.post(_SNP_REPORT, json={}, budget_seconds=0.05)
