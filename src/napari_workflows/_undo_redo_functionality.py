# most code modified from Arjan codes github library:
# https://github.com/ArjanCodes/2021-command-undo-redo/blob/main/LICENSE
# TODO mention it in case of implementation (MIT LICENSE)
from dataclasses import dataclass, field
from typing import List, Callable

import warnings
from ._workflow import Workflow, _layer_name_or_value
from napari import Viewer

@dataclass
class UndoRedoController:
    """
    This is a class that performs Actions that are handed to it and keeps
    track of which Actions were performed. Undo and redo can then be called with
    this class, reverting the changes made to a workflow

    Parameters
    ----------
    undo_stack: list[Action]
        List of Actions for which the undo function will be executed if 
        Undo_redo_controller.undo() is called

    redo_stack: list[Action]
        List of Actions for which the redo function will be executed if 
        Undo_redo_controller.undo() is called

    freeze_stacks: bool
        Actions can be performed on the workflow but undo and redo stacks
        remain unchanged when freeze_stacks = True
    """
    workflow: Workflow
    viewer: Viewer
    undo_stack: List[Workflow] = field(default_factory = list)
    redo_stack: List[Workflow] = field(default_factory = list)
    freeze_stacks: bool = False

    def execute(self, action: Callable) -> None:
        """
        Executes an action that is passed to it. In case the workflow changes
        through this action the previous workflow is added to the undo stack
        as a copy. If it is added to the undo stack the redo stack is also 
        cleared.

        Parameters
        ----------
        action: Callable
            An object which has an exeute command, which is initialised with 
            all parameters needed to perform the action
        """
        if not self.freeze_stacks:
            # we only want to update the undo stack if the workflow 
            # actually changes (otherwise undo won't function properly)

            if len(self.undo_stack) == 0: 
                self.undo_stack.append(
                    copy_workflow_state(self.workflow)
                    )
                self.redo_stack.clear()
                action()
                return
            if len(self.workflow._tasks.keys()) != len(self.undo_stack[-1]._tasks.keys()):
                self.undo_stack.append(
                    copy_workflow_state(self.workflow)
                )
                self.redo_stack.clear()
                action()
                return

            # workaround for situation where input image does not match 
            # any layer in viewer
            workflows_differ = False
            try:
                workflows_differ = (self.workflow._tasks != (self.undo_stack[-1])._tasks)
            except ValueError:
                warnings.warn("Cannot determine layer from image - Undo functionality impaired")
                
            if workflows_differ:  
                self.undo_stack.append(
                    copy_workflow_state(self.workflow)
                )
                self.redo_stack.clear()
        action()

    def undo(self) -> Workflow:
        """
        In case the undo stack is not empty this function returns the last entry
        of the undo stack and deletes it from the undo stack and adds the most 
        recent workflow to the redo stack.
        """
        if not self.undo_stack:
            return
        undone_workflow = self.undo_stack.pop()
        if not self.freeze_stacks:
            self.redo_stack.append(
                copy_workflow_state(self.workflow)
            )
        return undone_workflow

    def redo(self) -> Workflow:
        """
        In case the redo stack is not empty this function returns the last entry
        of the undo stack and deletes it from the undo stack
        """
        if not self.redo_stack:
            return
        redone_workflow = self.redo_stack.pop()
        if not self.freeze_stacks:
            self.undo_stack.append(
                copy_workflow_state(self.workflow)
            )
        return redone_workflow


def copy_workflow_state(workflow: Workflow) -> Workflow:
    """
    Returns a new Workflow object with identical parameters but not 
    including any input images
    """
    workflow_state = Workflow()
    for key, value in workflow._tasks.items():
        if callable(value[0]): 
            workflow_state.set(key, value)

    return workflow_state
