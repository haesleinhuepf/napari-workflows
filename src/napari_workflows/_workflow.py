import napari
from napari import Viewer
import numpy as np
import inspect
from dask.threaded import get as dask_get
from napari._qt.qthreading import thread_worker
import time


METADATA_WORKFLOW_VALID_KEY = "workflow_valid"

CURRENT_TIME_FRAME_DATA = "current_time_frame_data"


class Workflow():
    """
    The Workflow class encapsulates a dictionary that works as dask-task-graph. The task
    dictionary `str:tuple` spans a graph, because in the tuple, also strings can appear,
    that might be listed in the dictionary. When retrieving an image result using
    `get(task_name)`, all tasks are executed recursively that are necessary to retrieve
    the result of the specified task.
    """

    def __init__(self):
        # We start with an empty workflow with no tasks
        self._tasks = {}

    def set(self, name, func_or_data, *args, **kwargs):
        """
        Add a task to the workflow

        Parameters
        ----------
        name : str
            name of the task; typically corresponds to the layer name which is produced using the task
        func_or_data: callable or ndarray
            the function which produces the image data or the data itself
        args: list
        kwargs: dict

        """
        # TODO remove prints for testing

        

        # If it's not a function, just store the data
        if not callable(func_or_data):
            self._tasks[name] = func_or_data
            return
        
        
        # determine default parameters and apply them
        try:
            sig = inspect.signature(func_or_data)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            # Go through arguments and in case it's a callable, remove it
            # We should only have numbers, strings and images as parameters
            used_args = [value for key, value in bound.arguments.items()]
        except TypeError:
            used_args = list(args)
        '''
        # determine defaul parameters and apply them
        sig = inspect.signature(func_or_data)

        print(f'set workflow step: {name}')
        print(f'     args: {[arg for arg in args if not isinstance(arg, np.ndarray)]}')
        print(f'   kwargs: {kwargs}')
        print(f'signature: {sig}')
        
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()

        # Go through arguments and in case it's a callable, remove it
        # We should only have numbers, strings and images as parameters
        used_args = [value for key, value in bound.arguments.items()]
        '''
        for i in range(len(used_args)):
            if callable(used_args[i]):
                used_args[i] = None

        # Remove None parameters from the end
        while (used_args[-1] is None):
            used_args = used_args[:-1]

        # Store the task
        self._tasks[name] = tuple([func_or_data] + used_args)

    def remove(self, name):
        """
        Removes a given task from the workflow

        Parameters
        ----------
        name : str
            name of the taks to be removed, typically corresponds to the layer name
        """
        if name in self._tasks.keys():
            self._tasks.pop(name)

    def get(self, name):
        """
        Execute a task and all tasks that are necessary to retrieve the result.
        """
        return dask_get(self._tasks, name)

    def get_task(self, name):
        """
        Returns the tuple that represents a task.
        """
        return self._tasks[name]

    def set_task(self, name, task):
        """
        Replaces a given task.
        """
        self._tasks[name] = task

    def remove_all_except(self, names):
        """
        Removes all tasks except those specified by their names.

        Parameters
        ----------
        names: list or tuple of str
        """
        to_remove = [k for k in self._tasks.keys() if k not in names]
        for r in to_remove:
            del self._tasks[r]

    def roots(self):
        """
        Return all names of images that have no pre-processing steps.
        """
        origins = []

        keys_with_functions = [key for key, task in self._tasks.items() if callable(task[0])]

        for result, task in self._tasks.items():
            for source in task:
                if isinstance(source, str):
                    if not source in keys_with_functions:
                        if source not in origins:
                            origins.append(source)
        return origins

    def followers_of(self, item):
        """
        Return all names of images that are produced out of a given image.
        """
        followers = []
        for result, task in self._tasks.items():
            for source in task:
                if isinstance(source, str):
                    if source == item:
                        if result not in followers:
                            followers.append(result)
        return followers

    def sources_of(self, item):
        """
        Returns all names of images that need to be there to produce a given image.
        """
        if item not in self._tasks.keys():
            return []
        task = self._tasks[item]
        return [i for i in task if isinstance(i, str)]

    def leafs(self):
        """
        Returns all image names that have no further processing steps.
        """
        return [l for l in self._tasks.keys() if len(self.followers_of(l)) == 0]

    def clear(self):
        """
        Removes all workflow steps stored in self._tasks
        """
        self._tasks = {}

    def __str__(self):
        out = "Workflow:\n"
        for result, task in self._tasks.items():
            # Define new Parameters to print that don't include the napari viewer
            # This makes printing the workflow more readable
            print_params = tuple([param for param in task if not isinstance(param,Viewer)])

            out = out + result + " <- "+ str(print_params) + "\n"
        return out


class WorkflowManager():
    """
    The workflow manager is attached to a given napari Viewer once any Workflow step is executed.
    """

    @classmethod
    def install(cls, viewer: napari.Viewer):
        """
        Installs a workflow manager to a given napari Viewer (if not done earlier already) and returns it.
        """
        if not hasattr(WorkflowManager, "viewers_managers"):
            WorkflowManager.viewers_managers = {}

        if not viewer in WorkflowManager.viewers_managers.keys():
            WorkflowManager.viewers_managers[viewer] = WorkflowManager(viewer)
            # visualize intermediate results human-readable from top-left to bottom-right
            viewer.grid.stride = -1

        return WorkflowManager.viewers_managers[viewer]

    def __init__(self, viewer: napari.Viewer):
        from ._undo_redo_functionality import Undo_redo_controller
        """
        Use WorkflowManager.install(viewer) instead of this constructor.

        Parameters
        ----------
        viewer: napari.Viewer
        """
        self.viewer = viewer
        self.workflow = Workflow()
        self.undo_redo_controller = Undo_redo_controller(self.workflow)
        self._register_events_to_viewer(viewer)

        # The thread workwer will run in the background and check if images have to be recomputed.
        @thread_worker
        def loop_run():
           while True:  # endless loop
               time.sleep(0.2)
               yield self._update_invalid_layer()

        worker = loop_run()

        # in case some layer was updated by the thread worker, this function will receive the new data
        def update_layer(whatever):
            if whatever is not None:
                name, data = whatever
                if _viewer_has_layer(self.viewer, name):
                    self.viewer.layers[name].data = data

        # Start the loop
        worker.yielded.connect(update_layer)
        worker.start()

    def invalidate(self, items):
        """
        Invalidates layers with given names so that is it recomputed as soon as there is time for that.

        Parameters
        ----------
        items: list or tuple of str
            List of layer names to be invalidated
        """
        for f in items:
            if _viewer_has_layer(self.viewer, f):
                layer = self.viewer.layers[f]
                layer.metadata[METADATA_WORKFLOW_VALID_KEY] = False
                self.invalidate(self.workflow.followers_of(f))

    def update(self, target_layer, function, *args, **kwargs):
        """
        Update the task representing a given layer in the stored workflow by providing
        the function and parameters that generated the data in the layer.

        Other layers that were produced from the data stored in this layer are invalidated.

        Parameters
        ----------
        target_layer: napari.layers.Layer
        function: callable
        args: list
        kwargs: dict
        """
        from ._workflowmanager_commands import Update_workflow_step
        kwargs = {k:v for k,v in kwargs.items() if not ((isinstance(v, Viewer)) or (k == 'viewer'))}

        self.undo_redo_controller.execute(Update_workflow_step(
            self.workflow,
            self.viewer,
            target_layer,
            function,
            *args,
            **kwargs,
            )
        )

        # set result valid
        target_layer.metadata[METADATA_WORKFLOW_VALID_KEY] = True
        self.invalidate(self.workflow.followers_of(target_layer.name))

    def remove_zombies(self):
        from ._workflowmanager_commands import Remove_zombies
        self.undo_redo_controller.execute(Remove_zombies(
            self.workflow,
            self.viewer
            )
        )

    def to_python_code(self):
        """
        Output the current workflow in the viewer as python code.

        Returns
        -------
        str: python code
        """
        return _generate_python_code(self.workflow, self.viewer)

    def _update_invalid_layer(self):
        """
        Searches for the next layer that should be updated because it's invalid.
        """
        layer = self._search_first_invalid_layer(self.workflow.roots())
        if layer is None:
            return
        try:
            self.viewer.layers[layer.name].source.widget()
            layer.metadata[METADATA_WORKFLOW_VALID_KEY] = True
        except Exception as a:
            print("Error while updating", layer.name, a)

    def _search_first_invalid_layer(self, items):
        """
        Recursively searches for the next layer that sould be udpated in the graph of tasks.

        Parameters
        ----------
        items: list[str]
            List of task names; typically starts at roots().

        Returns
        -------
        str: task/layer name that should be updated
        """
        for i in items:
            if _viewer_has_layer(self.viewer, i):
                layer = self.viewer.layers[i]
                if _layer_invalid(layer):
                    return layer
        for i in items:
            invalid_follower = self._search_first_invalid_layer(self.workflow.followers_of(i))
            if invalid_follower is not None:
                return invalid_follower

        return None

    def _register_events_to_viewer(self, viewer: napari.Viewer):
        """
        This function internally registers events at a given viewer so that we can
        react if something is happening, e.g. layers are added/removed.
        """

        viewer.dims.events.current_step.connect(self._slider_updated)
        viewer.layers.events.inserted.connect(self._layer_added)
        viewer.layers.events.removed.connect(self._layer_removed)
        viewer.layers.selection.events.changed.connect(self._layer_selection_changed)

    def _register_events_to_layer(self, layer):
        """
        This function adds events to a layer so that we can react, e.g. in case
        its data is updated.
        """
        layer.events.data.connect(self._layer_data_updated)

    def _layer_data_updated(self, event):
        #print("Layer data updated", event.source, type(event.source))
        event.source.metadata[METADATA_WORKFLOW_VALID_KEY] = True
        for f in self.workflow.followers_of(str(event.source)):
            if _viewer_has_layer(self.viewer, f):
                layer = self.viewer.layers[f]
                self.invalidate(self.workflow.followers_of(f))

    def _layer_added(self, event):
        #print("Layer added", event.value, type(event.value))
        self._register_events_to_layer(event.value)

    def _layer_removed(self, event):
        from ._workflowmanager_commands import Layer_removed
        #print("Layer removed", event.value, type(event.value))
        self.undo_redo_controller.execute(Layer_removed(
            self.workflow,
            event.value.name
            )
        )

    def _slider_updated(self, event):
        slider = event.value
        # print("Slider updated", event.value, type(event.value))
        if len(slider) == 4: # a time-slider exists
            for l in self.viewer.layers:
                if len(l.data.shape) == 4:
                    self.invalidate(self.workflow.followers_of(l.name))

    def _layer_selection_changed(self, event):
        pass
        #print("Layer selection changed", event)


def _viewer_has_layer(viewer: napari.Viewer, name: str):
    """
    Checks if a viewer contains a layer named as specified.

    Parameters
    ----------
    viewer: napari.Viewer
    name: str

    Returns
    -------
    bool
        True if a layer with name exists in viewer.
        False otherwise.
    """
    try:
        layer = viewer.layers[name]
        return layer is not None
    except KeyError:
        return False


def _get_layer_from_data(viewer: napari.Viewer, data):
    """
    Returns the layer in viewer that has the given data or None if such a layer doesn't exist.
    """
    for layer in viewer.layers:
        if layer.data is data:
            return layer
        try:
            # todo: this should live in napari-time-slicer
            if layer.metadata[CURRENT_TIME_FRAME_DATA] is data:
                return layer
        except KeyError:
            pass
    return None


def _generate_python_code(workflow: Workflow, viewer: napari.Viewer):
    """
    Takes a Workflow and a viewer an generates python code corresponding to the workflow.
    Precondition: The used functions must be compatible with Workflows and register their
    functionality.

    Parameters
    ----------
    workflow: Workflow
        The workflow which should be converted to code.
    viewer: napari.Viewer
        The viewer where the workflow was set up.

    Returns
    -------
    str
        python code
    """
    imports = []
    code = []

    roots = workflow.roots()

    def python_conform_variable_name(value):
        if isinstance(value, str):
            value = value.replace("[", "_") \
                .replace("]", "_") \
                .replace(" ", "_") \
                .replace("(", "_") \
                .replace(")", "_") \
                .replace(".", "_") \
                .replace("-", "_")\
                .replace(":", "_")\
                .replace(";", "_")\
                .replace(",", "_")\
                .replace(".", "_")
            if value[0] in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
                value = "img_" + value
        return str(value)

    def build_output(list_of_items, func_to_follow):
        """
        This function is called recursively to generate code that represents the
        image data flow graph stored in workflow.

        Parameters
        ----------
        list_of_items: list[str]
            layer names that should be computed iteratively
        func_to_follow: callable
            This function can be called with a single layer name and will return a list of names that
            are related to the layer with the given name. This function can for example be
            `workflow.followers_of()`.

        Returns
        -------
        str
            python code
        """
        for key in list_of_items:
            result_name = python_conform_variable_name(key)
            try:
                # Retrieve the task that corresponds to this layer
                task = workflow.get_task(key)

                # split it into the used function and corresponding arguments
                function = task[0]
                arguments = task[1:]
                if arguments[-1] is None:
                    arguments = arguments[:-1]

                # determine package and module
                package_path = function.__module__.split(".")
                module = package_path[0]
                new_import = "import " + module

                # load the module
                loaded_module = __import__(module)

                # if the module has an alias, use this alias in the code
                try:
                    alias = loaded_module.__common_alias__
                    new_import = new_import + " as " + alias

                    if len(package_path) == 1:
                        module = alias
                    else:
                        module = alias + "." + ".".join(package_path[1:])
                except:
                    pass

                # add imports
                if new_import not in imports:
                    imports.append(new_import)

                # put together code that calls the function
                arg_str = ", ".join([python_conform_variable_name(a) for a in arguments])
                code.append("# " + function.__name__.replace("_", " "))
                code.append(f"{result_name} = {module}.{function.__name__}({arg_str})")

                # add code that shows the result in a layer
                if _viewer_has_layer(viewer, key):
                    if isinstance(viewer.layers[key], napari.layers.Labels):
                        code.append(f"viewer.add_labels({result_name}, name='{key}')")
                    else:
                        code.append(f"viewer.add_image({result_name}, name='{key}')")
            except KeyError:
                code.append(f"{result_name} = viewer.layers['{key}'].data")
            code.append("")
            build_output(func_to_follow(key), func_to_follow)

    build_output(workflow.roots(), workflow.followers_of)
    from textwrap import dedent

    # put some code in front
    preamble = dedent("""
        import napari

        if 'viewer' not in globals():
            viewer = napari.Viewer()
        """).strip()

    complete_code = "\n".join(imports) + "\n" + preamble + "\n\n" + "\n".join(code) + "\n"

    # format the code PEP8
    import autopep8
    complete_code = autopep8.fix_code(complete_code)

    return complete_code

def _layer_name_or_value(value, viewer: napari.Viewer):
    """
    Checks if there is a layer in the viewer where layer.data == value. If so,
    it returns the name of the layer. Otherwise, it returns value.

    Parameters
    ----------
    value: ndarray
    viewer: napari.Viewer

    Returns
    -------
    str or ndarray
    """
    layer = _get_layer_from_data(viewer, value)
    if layer is not None:
        return layer.name
    return value

def _layer_invalid(layer):
    """
    Returns if the data in a given layer is valid or should be re-computed because parameters were changed.
    """
    try:
        return layer.metadata[METADATA_WORKFLOW_VALID_KEY] == False
    except KeyError:
        return False


# todo: this function should live in napari-time-slicer
def _break_down_4d_to_2d_kwargs(arguments, current_timepoint, viewer):
    """
    Goes through a dictionary of arguments and identifies image data arguments with 4 dimensions.
    If there is any layer in the viewer where layer.data corresponds to this image, it assumes that
    the first dimension corresponds to time and will replace this 4D dataset with the 3D image at
    the given timepoint. If the 3D dataset has only one element in the first dimension, only one slice,
    it will be replaced by the 2D dataset.

    Parameters
    ----------
    arguments: dict
        dictionary of function arguments
    current_timepoint: int
        current timepoint selected in the Viewer
    viewer: napari.Viewer
        The viewer is necessary to find out if a string in the argument list corresponds to a layer
        in the viewer.
    """
    for key, value in arguments.items():
        if isinstance(value, np.ndarray) or str(type(value)) in ["<class 'cupy._core.core.ndarray'>",
                                                                 "<class 'dask.array.core.Array'>"]:
            if len(value.shape) == 4:
                layer = _get_layer_from_data(viewer, value)
                new_value = value[current_timepoint]
                if new_value.shape[0] == 1:
                    new_value = new_value[0]
                arguments[key] = new_value
                layer.metadata[CURRENT_TIME_FRAME_DATA] = new_value


# todo: this function should live in napari-time-slicer
def _break_down_4d_to_2d_args(arguments, current_timepoint, viewer):
    """
        Goes through a list of arguments and identifies image data arguments with 4 dimensions.
        If there is any layer in the viewer where layer.data corresponds to this image, it assumes that
        the first dimension corresponds to time and will replace this 4D dataset with the 3D image at
        the given timepoint. If the 3D dataset has only one element in the first dimension, only one slice,
        it will be replaced by the 2D dataset.

        Parameters
        ----------
        arguments: list
            list of function arguments
        current_timepoint: int
            current timepoint selected in the Viewer
        viewer: napari.Viewer
            The viewer is necessary to find out if a string in the argument list corresponds to a layer
            in the viewer.
        """
    for i in range(len(arguments)):
        value = arguments[i]
        if isinstance(value, np.ndarray) or str(type(value)) in ["<class 'cupy._core.core.ndarray'>",
                                                                 "<class 'dask.array.core.Array'>"]:
            if len(value.shape) == 4:
                layer = _get_layer_from_data(viewer, value)
                new_value = value[current_timepoint]
                if new_value.shape[0] == 1:
                    new_value = new_value[0]
                arguments[i] = new_value
                layer.metadata[CURRENT_TIME_FRAME_DATA] = new_value


'''
old code for set workflow step
# determine defaul parameters and apply them
        sig = inspect.signature(func_or_data)

        print(f'set workflow step: {name}')
        print(f'     args: {[arg for arg in args if not isinstance(arg, np.ndarray)]}')
        print(f'   kwargs: {kwargs}')
        print(f'signature: {sig}')
        
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()

        # Go through arguments and in case it's a callable, remove it
        # We should only have numbers, strings and images as parameters
        used_args = [value for key, value in bound.arguments.items()]
'''