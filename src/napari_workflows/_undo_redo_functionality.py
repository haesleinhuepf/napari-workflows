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

    freeze: bool
        If True controller will not carry out any actions on the workflow
        when freeze = True

    freeze_stacks: bool
        Actions can be performed on the workflow but undo and redo stacks
        remain unchanged when freeze_stacks = True
    """
    workflow: Workflow
    undo_stack: list[Workflow] = field(default_factory = list)
    redo_stack: list[Workflow] = field(default_factory = list)
    freeze_stacks: bool = False

    def execute(self,action: Action) -> None:
        self.redo_stack.clear()
        if not self.freeze_stacks:
            self.undo_stack.append(
                copy_workflow_state(self.workflow)
                )
        action.execute()

    def undo(self) -> Workflow:
        if not self.undo_stack:
            return
        undone_workflow = self.undo_stack.pop()
        if not self.freeze_stacks:
            self.redo_stack.append(undone_workflow)
        return undone_workflow

    def redo(self) -> None:
        if not self.redo_stack:
            return
        redone_workflow = self.undo_stack.pop()
        if not self.freeze_stacks:
            self.undo_stack.append(redone_workflow)
        return redone_workflow
    
def copy_workflow_state (workflow: Workflow):
    workflow_state = Workflow()
    for key, value in workflow._tasks.items():
        if callable(value[0]): 
            workflow_state.set(key, value)

    return workflow_state