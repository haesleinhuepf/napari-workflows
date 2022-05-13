from ._workflow import Workflow, _layer_name_or_value
from napari import Viewer
from numpy import ndarray

class Update_workflow_step:
    """
    Action which updates a given workflow step based on a target layer and function
    including args and kwargs.

    Parameters
    ----------
    """
    def __init__(self, workflow: Workflow, viewer: Viewer, target_layer, function, *args, **kwargs) -> None:
        self.workflow = workflow
        self.viewer = viewer
        self.target_layer = target_layer
        self.function = function
        self.args = args
        self.kwargs = kwargs

        try:
            self.old_task = workflow._tasks[target_layer.name]
        except KeyError:
            self.old_task = None

    def execute(self) -> None:
        # setting of workflow step
        self.workflow.set(self.target_layer.name, self.function, *self.args, **self.kwargs)

        # plus the remove zombies function
        kill_zombies(self.viewer,self.workflow)


class Remove_zombies:
    """
    Action which when executed removes workflow steps not connected to any
    further workflow steps
    """
    def __init__(self, workflow: Workflow, viewer = Viewer) -> None:
        self.workflow = workflow
        self.viewer = viewer

    def execute(self) -> None:
        kill_zombies(self.viewer,self.workflow)

class Layer_removed:
    """
    Action which when executed removes a workflow step with name specified
    to the object
    """
    def __init__(self, workflow: Workflow, name: str) -> None:
        self.workflow = workflow
        self.name = name
        try:
            self.old_task = workflow._tasks[name]
        except KeyError:
            self.old_task = None

    def execute(self) -> None:
        self.workflow.remove(self.name)

def kill_zombies(viewer, workflow):
    """
    Removes workflow steps which are not represented by a layer
    """
    layer_names = [layer.name for layer in viewer.layers]
    workflow.remove_all_except(layer_names)