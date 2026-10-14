"""回归：外层模型等待窗口不得被 langchain_openai 的 stream_chunk_timeout 抢先打断。

实测 102 批次两项（复方氨基酸、左乙拉西坦）在约 120 秒内容静默后抛
StreamChunkTimeoutError（langchain_openai 默认值），使 GLM 的 300 秒等待窗口失效，
恢复路径也在同一处失败。这里锁死"stream_chunk_timeout > 外层窗口"。
"""
from virtual_reactor_api.agent_runtime import _create_model
from virtual_reactor_api.research_limits import model_wait_seconds


def test_stream_chunk_timeout_exceeds_glm_wait_window():
    model = _create_model('openai:glm-5.2', 'test-no-network', 'https://example.org/api/paas/v4')
    assert model.stream_chunk_timeout is not None
    assert model.stream_chunk_timeout > model_wait_seconds('openai:glm-5.2')
    assert model.stream_chunk_timeout > model_wait_seconds('openai:glm-5.2', recovery=True)


def test_stream_chunk_timeout_exceeds_astra_wait_window_and_keeps_responses():
    model = _create_model('openai:gpt-6-astra', 'test-no-network', 'https://example.org/v1')
    assert model.stream_chunk_timeout is not None
    assert model.stream_chunk_timeout > model_wait_seconds('openai:gpt-6-astra')
    assert model.streaming is True
