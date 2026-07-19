async def test_history_roundtrip(db):
    messages = [
        {'role': 'system', 'content': 'sys'},
        {'role': 'assistant', 'content': None,
         'tool_calls': [{'id': 't1', 'type': 'function',
                         'function': {'name': 'f', 'arguments': '{"a": 1}'}}]},
        {'role': 'tool', 'tool_call_id': 't1', 'content': 'result'},
        {'role': 'user', 'content': [{'type': 'image_url',
                                      'image_url': {'url': 'data:image/jpeg;base64,xxx'}}]},
    ]
    await db.save_history(1, messages)
    assert await db.get_history(1) == messages
    assert await db.delete_history(1) is True
    assert await db.get_history(1) is None
    assert await db.delete_history(1) is False


async def test_stats_accumulate(db):
    await db.add_stats(1, messages_sent=1, prompt_tokens=10, cost_usd=0.1)
    await db.add_stats(1, messages_sent=1, completion_tokens=5, cost_usd=0.2)
    stats = await db.get_stats(1)
    assert stats['messages_sent'] == 2
    assert stats['prompt_tokens'] == 10
    assert stats['completion_tokens'] == 5
    assert abs(stats['cost_usd'] - 0.3) < 1e-9


async def test_rate_limit_boundary(db):
    # exactly `limit` messages are allowed
    for _ in range(3):
        allowed, _ = await db.rate_check_and_record(1, 3600, 3)
        assert allowed
    allowed, used = await db.rate_check_and_record(1, 3600, 3)
    assert not allowed
    assert used == 3


async def test_rate_limit_check_does_not_consume(db):
    for _ in range(5):
        allowed, used = await db.rate_check_and_record(1, 3600, 3, record=False)
        assert allowed
        assert used == 0


async def test_selected_model_and_style(db):
    assert await db.get_selected_model(1) is None
    await db.set_selected_model(1, 'backup')
    await db.set_style(1, 'Alice')
    assert await db.get_selected_model(1) == 'backup'
    assert await db.get_style(1) == 'Alice'


async def test_files_registry(db):
    await db.upsert_file('common', 'a.pdf', 'summary A', True)
    await db.upsert_file('42', 'b.txt', None, False)
    await db.upsert_file('42', 'b.txt', 'summary B', True)  # upsert
    files = await db.list_files('42')
    assert len(files) == 1
    assert files[0]['summary'] == 'summary B'
    assert await db.delete_files('42') == 1
    assert await db.list_files('42') == []
