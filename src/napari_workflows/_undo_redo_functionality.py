# most code modified from Arjan codes github library:
# https://github.com/ArjanCodes/2021-command-undo-redo/blob/main/LICENSE
# TODO mention it in case of implementation (MIT LICENSE)
from dataclasses import dataclass, field
from typing import Protocol
from ._workflow import Workflow

class Action(Protocol):
    """
    General form of how and Action is structured
    """
    def execute() -> None:
        ...


@dataclass
class Undo_redo_controller:
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
    undo_stack: list[Workflow] = field(default_factory = list)
    redo_stack: list[Workflow] = field(default_factory = list)
    freeze_stacks: bool = False

    def execute(self,action: Action) -> None:
        if not self.freeze_stacks:
            # we only want to update the undo stack if the workflow 
            # actually changes (otherwise undo won't function properly)
            if len(self.undo_stack) == 0: 
                self.undo_stack.append(
                    copy_workflow_state(self.workflow)
                    )
                self.redo_stack.clear()
                action.execute()
                return
            if len(self.workflow._tasks.keys()) != len(self.undo_stack[-1]._tasks.keys()):
                self.undo_stack.append(
                    copy_workflow_state(self.workflow)
                )
                self.redo_stack.clear()
            elif self.workflow._tasks != self.undo_stack[-1]._tasks:
                self.undo_stack.append(
                    copy_workflow_state(self.workflow)
                )
                self.redo_stack.clear()
        action.execute() 

    def undo(self) -> Workflow:
        if not self.undo_stack:
            return
        undone_workflow = self.undo_stack.pop()
        if not self.freeze_stacks:
            self.redo_stack.append(
                copy_workflow_state(self.workflow)
            )
        return undone_workflow

    def redo(self) -> Workflow:
        if not self.redo_stack:
            return
        redone_workflow = self.redo_stack.pop()
        if not self.freeze_stacks:
            self.undo_stack.append(
                copy_workflow_state(self.workflow)
            )
        return redone_workflow
    
def copy_workflow_state (workflow: Workflow) -> Workflow:
    """
    Returns a new Workflow object with identical parameters but not 
    including any input images
    """
    workflow_state = Workflow()
    for key, value in workflow._tasks.items():
        if callable(value[0]): 
            workflow_state.set(key, value)

    return workflow_state