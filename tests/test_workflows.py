from pytest import fixture
from napari_workflows import Workflow

@fixture
def data_task() -> Workflow:
    """
    A workflow that only has a data key, without any callables
    """
    w = Workflow()
    w.set("x", 10)
    return w

def test_data_task_roots(data_task: Workflow):
    data_task.roots()

def test_data_task_leafs(data_task: Workflow):
    data_task.leafs()
