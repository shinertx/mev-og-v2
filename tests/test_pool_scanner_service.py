from adapters.pool_scanner_service import create_app, MOCK_L3_POOLS


def test_health_endpoint() -> None:
    app = create_app()
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"


def test_pools_endpoint_filter(monkeypatch) -> None:
    from adapters import pool_scanner_service

    monkeypatch.setattr(
        pool_scanner_service,
        "MOCK_POOLS",
        [
            {
                "address": "0x1",
                "token0": "WETH",
                "token1": "USDC",
                "fee": 0.0,
                "liquidity": 1.0,
                "tick": 0,
                "extra": {"dex": "uniswap", "chain": "ethereum"},
            }
        ],
    )
    app = pool_scanner_service.create_app()
    client = app.test_client()
    resp = client.get("/pools?dex=uniswap&chain=ethereum")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data and isinstance(data, list)
    assert all(p["extra"]["chain"] == "ethereum" for p in data)


def test_l3_pools() -> None:
    app = create_app()
    client = app.test_client()
    resp = client.get("/l3_pools")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == MOCK_L3_POOLS
