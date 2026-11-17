import importlib
import os
import py_compile
from pathlib import Path

import pytest

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

MODULES = [
    "hawkeye_assistant",
    "hawkeye_assistant.config",
    "hawkeye_assistant.llm",
    "hawkeye_assistant.agent.classify",
    "hawkeye_assistant.memory.store",
    "hawkeye_assistant.optimizer.opro",
    "hawkeye_assistant.evaluation.evaluate",
    "hawkeye_assistant.training.train",
    "hawkeye_assistant.tools",
    "hawkeye_assistant.api.app",
    "hawkeye_assistant.hawkeye",
    "hawkeye_assistant.hawkeye.client",
    "hawkeye_assistant.hawkeye.schemas",
    "hawkeye_assistant.hawkeye.auth",
]

UI_SCRIPT = Path(__file__).resolve().parents[1] / "src" / "hawkeye_assistant" / "ui" / "streamlit_app.py"


@pytest.mark.parametrize("name", MODULES)
def test_import(name):
    importlib.import_module(name)


def test_streamlit_app_compiles():
    # Importing the UI would execute the whole Streamlit page, so only compile it.
    py_compile.compile(str(UI_SCRIPT), doraise=True)


def test_paths_point_at_project_files():
    from hawkeye_assistant import config

    assert config.TRAIN_FILE.is_file()
    assert config.TEST_FILE.is_file()
    assert config.DEMO_FILE.is_file()
    assert config.MEMORY_DB_DIR.parent == config.STORAGE_DIR
    assert config.RESULTS_FILE.parent == config.STORAGE_DIR
