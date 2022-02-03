from ._workflow import Workflow
import numpy as np

def save_workflow(filename:str, workflow:Workflow):
    """Save a workflow to a file on disk.

    Parameters
    ----------
    filename: str
    workflow: Workflow
    """
    # Filter out workflow steps that do not represent a processing step
    workflow_to_save = Workflow()
    for key, value in workflow._tasks.items():
        if not isinstance(value[0], np.ndarray):
            workflow_to_save.set(key, value)
    
    # Save the remaining steps to disk
    from yaml import dump
    with open(filename, 'w') as stream:
        dump(workflow_to_save,stream)

def load_workflow(filename:str) -> Workflow:
    """Load a workflow from a file on disk.

    Parameters
    ----------
    filename: str

    Returns
    -------
    Workflow
    """
    from yaml import unsafe_load
    with open(filename, "rb") as stream:
        return unsafe_load(stream)