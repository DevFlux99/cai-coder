from pathlib import Path

from agent.utils import common_util

def test_utils_find_project_root():
    path = common_util.find_project_root()
    assert  path == Path(__file__).parent.parent

    path = common_util.find_project_root(Path(__file__))
    assert  path == Path(__file__).parent.parent


def test_init_workspace_templates(tmp_path):
    common_util.init_workspace_templates(tmp_path)


def test_init_workspace_template_files(tmp_path):
    adds = common_util.init_workspace_templates(tmp_path)
    for item in adds:
        print(item)