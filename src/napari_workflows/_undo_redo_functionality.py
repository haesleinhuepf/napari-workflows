from dataclasses import dataclass
from typing import Protocol
from _workflow import Workflow
from napari import Viewer
from _workflow import _layer_name_or_value

class Action(Protocol):
    def execute() -> None:
        ...
    
    def undo() -> None:
        ...

    def redo() -> None:
        ...


@dataclass
class Undo_redo_controller:
    undo_stack: list = []
    redo_stack: list = []

    def execute(self,action: Action) -> None:
        action.execute()
        self.redo_stack.clear()
        self.undo_stack.append(action)

    def undo(self) -> None:
        if not self.undo_stack:
            return
        action = self.undo_stack.pop()
        action.undo()
        self.redo_stack.append(action)

    def redo(self) -> None:
        if not self.redo_stack:
            return
        action = self.redo_stack.pop()
        action.redo()
        self.undo_stack.append(action)


class update_workflow_step:
    '''target_layer: 
    function: function
    args: 
    kwargs: **kwargs
    '''
    def __init__(self,workflow: Workflow, viewer: Viewer, target_layer, function: function, *args, **kwargs) -> None:
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

    def execute(self):
        args = list(self.args)
        for i in range(len(args)):
            args[i] = _layer_name_or_value(args[i], self.viewer)
        if isinstance(args[-1], Viewer):
            args = args[:-1]
        args = tuple(args)
        self.workflow.set(self.target_layer.name, function, *args, **self.kwargs)

    def undo(self):
        # set the workflow step to what it was before
        # delete the new wf step if one was created
        if not self.old_function:
            self.workflow.remove(self.target_layer.name)

        # change the values to the old ones otherwise
        else:
            self.workflow[self.target_layer.name] = self.old_task

    def redo(self):
        #for now just the copied execute
        args = list(self.args)
        for i in range(len(args)):
            args[i] = _layer_name_or_value(args[i], self.viewer)
        if isinstance(args[-1], Viewer):
            args = args[:-1]
        args = tuple(args)
        self.workflow.set(self.target_layer.name, function, *args, **self.kwargs)
