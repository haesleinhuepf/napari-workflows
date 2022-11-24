import numpy as np
import inspect
from dask.threaded import get as dask_get
from napari._qt.qthreading import thread_worker
import time
from functools import partial

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
        # If it's not a function, just store the data
        if not callable(func_or_data):
            self._tasks[name] = func_or_data
            return

        # determine defaul parameters and apply them
        sig = inspect.signature(func_or_data)

        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        # Go through arguments and in case it's a callable, remove it
        # We should only have numbers, strings and images as parameters
        used_args = [value for key, value in bound.arguments.items()]

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
            print_params = tuple([param for param in task if not "napari.viewer.Viewer" in str(type(param))])

            out = out + result + " <- "+ str(print_params) + "\n"
        return out


class WorkflowManager():
    """
    The workflow manager is attached to a given napari Viewer once any Workflow step is executed.
    """

    @classmethod
    def install(cls, viewer: "napari.Viewer", _for_testing:bool = False):
        """
        Installs a workflow manager to a given napari Viewer (if not done earlier already) and returns it.
        """
        if not hasattr(WorkflowManager, "viewers_managers"):
            WorkflowManager.viewers_managers = {}

        if not viewer in WorkflowManager.viewers_managers.keys():
            WorkflowManager.viewers_managers[viewer] = WorkflowManager(viewer, _for_testing)
            # visualize intermediate results human-readable from top-left to bottom-right
            viewer.grid.stride = -1

        return WorkflowManager.viewers_managers[viewer]

    def __init__(self, viewer: "napari.Viewer", _for_testing:bool = False):
        from ._undo_redo_functionality import UndoRedoController
        """
        Use WorkflowManager.install(viewer) instead of this constructor.

        Parameters
        ----------
        viewer: "napari.Viewer"
        """
        self.viewer = viewer
        self.workflow: Workflow = Workflow()
        self.undo_redo_controller = UndoRedoController(self.workflow, viewer)
        self._register_events_to_viewer(viewer)
        self.worker = None
        self._is_active = True

        # The thread workwer will run in the background and check if images have to be recomputed.
        @thread_worker
        def loop_run():
           while True:  # endless loop
               time.sleep(0.05)
               yield self._update_invalid_layer()


        if not _for_testing:
            self.worker = loop_run()

            # in case some layer was updated by the thread worker, this function will receive the new data
            def update_layer(whatever):
                if whatever is not None:
                    name, data = whatever
                    if _viewer_has_layer(self.viewer, name):
                        self.viewer.layers[name].data = data

            # Start the loop
            self.worker.yielded.connect(update_layer)
            self.worker.start()

    def pause_update(self) -> None:
        """Temporarily halt the automatic update."""
        self.worker.pause()
        self._is_active = False

    def resume_update(self) -> None:
        """Resume the automatic update."""
        self.worker.resume()
        self._is_active = True

    def is_update_paused(self) -> bool:
        """Return the current worker state."""
        return not self._is_active

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
        # preprocessing of args and kwargs
        from napari import Viewer
        kwargs = {k:v for k,v in kwargs.items() if not ((isinstance(v, Viewer)) or (k == 'viewer'))}
        args = list(args)
        for i in range(len(args)):
            if is_image(args[i]) or type(args[i]) == tuple:
                args[i] = _layer_name_or_value(args[i], self.viewer)
                if not isinstance(args[i], str):
                    # Workaround: If we don't stop storing this here, it crashes later
                    # because it passes strings as images to image processing functions
                    print("Finding layer failed. Change was not stored")
                    return
        if isinstance(args[-1], Viewer):
            args = args[:-1]
        args = tuple(args)

        self.undo_redo_controller.execute(partial(self._update_workflow_step, target_layer, function, args, kwargs))

        # set result valid
        target_layer.metadata[METADATA_WORKFLOW_VALID_KEY] = True
        self.invalidate(self.workflow.followers_of(target_layer.name))

    def _update_workflow_step(self, target_layer, function, args, kwargs):
        # setting of workflow step
        self.workflow.set(target_layer.name, function, *args, **kwargs)
        self._remove_zombies()

    def remove_zombies(self):
        """
        Removes workflow steps which are not represented by a layer
        This step is recorded for undo/redo
        """
        self.undo_redo_controller.execute(self._remove_zombies)

    def _remove_zombies(self):
        """
        Removes workflow steps which are not represented by a layer
        """
        layer_names = [layer.name for layer in self.viewer.layers]
        self.workflow.remove_all_except(layer_names)

    def to_python_code(self, notebook=False, use_napari:bool=True):
        """
        Output the current workflow in the viewer as python code.

        Returns
        -------
        str: python code
        """
        return _generate_python_code(self.workflow, self.viewer, notebook=notebook, use_napari=use_napari)

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

    def _register_events_to_viewer(self, viewer: "napari.Viewer"):
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
        """
        Remove a layer from the workflow as specified by a napari event
        This step is recorded for undo/redo
        """
        self.undo_redo_controller.execute(partial(self._remove_layer_from_workflow, event.value.name))

    def _remove_layer_from_workflow(self, name):
        """
        Remove a layer from the workflow as specified by name
        """
        self.workflow.remove(name)

    def _slider_updated(self, event):
        import napari
        slider = event.value
        # print("Slider updated", event.value, type(event.value))
        if len(slider) == 4: # a time-slider exists
            for l in self.viewer.layers:
                if (not isinstance(l, (napari.layers.Labels, napari.layers.Image))) or len(l.data.shape) == 4:
                    self.invalidate(self.workflow.followers_of(l.name))

    def _layer_selection_changed(self, event):
        pass
        #print("Layer selection changed", event)


def _viewer_has_layer(viewer: "napari.Viewer", name: str):
    """
    Checks if a viewer contains a layer named as specified.

    Parameters
    ----------
    viewer: "napari.Viewer"
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


def _get_layer_from_data(viewer: "napari.Viewer", data):
    """
    Returns the layer in viewer that has the given data or None if such a layer doesn't exist.
    """
    if viewer is None:
        return None
    for layer in viewer.layers:
        if layer.data is data:
            return layer
        try:
            # todo: this should live in napari-time-slicer
            if layer.metadata[CURRENT_TIME_FRAME_DATA] is data:
                return layer
        except KeyError:
            pass

        if type(data) == tuple and type(layer.data) == tuple:
            equal_data = True
            for a, b in zip(data, layer.data):
                if a is not b:
                    equal_data = False
            if equal_data:
                return layer

    return None


def _generate_python_code(workflow: Workflow, viewer: "napari.Viewer", notebook: bool = False, use_napari:bool = True):
    """
    Takes a Workflow and a viewer an generates python code corresponding to the workflow.
    Precondition: The used functions must be compatible with Workflows and register their
    functionality.

    Parameters
    ----------
    workflow: Workflow
        The workflow which should be converted to code.
    viewer: "napari.Viewer"
        The viewer where the workflow was set up.
    notebook: bool, optional
        In case code is generated for jupyter notebooks, it looks a bit different.

    Returns
    -------
    str
        python code
    """
    imports = ["from skimage.io import imread"]
    code = []

    import dask
    order = dask.order.order(workflow._tasks)

    roots = order.keys()

    image_variable_names = {}

    def python_conform_variable_name(value):
        if isinstance(value, str):
            if value not in image_variable_names:
                # Make a short and readable variable name, e.g. turn a layer
                # "Resut of Gaussian blur" into "image1_gb".
                temp = value
                temp = temp.replace("Result of ", "")
                temp = temp.replace(" result", "")
                temp = "".join([t[0] for t in temp.split("_")])
                new_name = "image" + str(len(image_variable_names)) + "_" + temp
                image_variable_names[value] = new_name

            return image_variable_names[value]
        else:
            return str(value)

    def build_output(list_of_items):
        """
        This function is called to generate code that represents the
        image data flow graph stored in workflow. The graph should be
        sorted in advance, e.g. using dask.order.order() and the resulting
        sorted list of keys can be passed here.

        Parameters
        ----------
        list_of_items: list[str]
            layer names that should be computed iteratively

        Returns
        -------
        str
            python code
        """
        comment_start = "# "
        if notebook:
            # jupytext will render "# ##" as an h2 header in ipynb
            comment_start = "# ## "

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

                # document version
                try:
                    version = loaded_module.__version__
                    new_import = new_import + " # version " + str(version)
                except:
                    pass

                # add imports
                if new_import not in imports:
                    imports.append(new_import)

                # put together code that calls the function
                arg_str = ", ".join([python_conform_variable_name(a) for a in arguments])


                code.append(comment_start + function.__name__.replace("_", " ") + "\n")
                code.append(f"{result_name} = {module}.{function.__name__}({arg_str})")

                if use_napari:
                    _viewer_add_image_and_notebook_screenshot(code, viewer, notebook, result_name, key)
                elif notebook:
                    code.append(result_name + "\n")

            except KeyError:
                try:
                    layer = viewer.layers[key]
                    if notebook:
                        code.append(comment_start + f"Loading '{key}'")

                    if layer.source.path is not None:
                        if notebook:
                            code.append(f"")

                        code.append(f"{result_name} = imread(\"" + str(layer.source.path).replace("\\", "/") + "\")")
                        if use_napari:
                            _viewer_add_image_and_notebook_screenshot(code, viewer, notebook, result_name, key)
                        elif notebook:
                            code.append(result_name + "\n")

                    else:
                        if notebook:
                            code.append(f"# Please enter code for loading '{key}' here.")
                            code.append(f"")
                            code.append(f"#filename = 'path/to/image.tif'")
                            code.append(f"#{result_name} = imread(filename)")
                        code.append(f"{result_name} = viewer.layers['{key}'].data")
                    code.append("")
                except KeyError:
                    # The layer doesn't exist
                    pass


    build_output(workflow.roots())
    build_output(roots)

    from textwrap import dedent

    # put some code in front
    if use_napari:
        if not notebook:
            preamble = dedent("""
                import napari
                if 'viewer' not in globals():
                    viewer = napari.Viewer()
                """).strip()
        else:
            preamble = dedent("""
                import napari
                viewer = napari.Viewer()
                """).strip()
    else:
        preamble = ""

    if len(viewer.dims.current_step) > 3:
        preamble = preamble + "\n\n" + dedent("""
            # ## A note on processing timelapse data
            # This code was generated to process a single timepoint of a timelapse dataset.
            # To process all time points, you need to program a for-loop as shon here:
            # https://haesleinhuepf.github.io/BioImageAnalysisNotebooks/33_batch_processing/12_process_folders.html
            """).strip()

    complete_code = "\n".join(imports) + "\n" + preamble + "\n\n" + "\n".join(code) + "\n"

    # format the code PEP8
    import autopep8
    complete_code = autopep8.fix_code(complete_code)

    return complete_code

def _viewer_add_image_and_notebook_screenshot(code, viewer, notebook, result_name, key):
    import napari

    # add code that shows the result in a layer
    if _viewer_has_layer(viewer, key):
        if isinstance(viewer.layers[key], napari.layers.Labels):
            code.append(f"viewer.add_labels({result_name}, name='{key}')")
        else:
            code.append(f"viewer.add_image({result_name}, name='{key}')")

        if notebook:
            code.append("napari.utils.nbscreenshot(viewer)")
        code.append("")

def _layer_name_or_value(value, viewer: "napari.Viewer"):
    """
    Checks if there is a layer in the viewer where layer.data == value. If so,
    it returns the name of the layer. Otherwise, it returns value.

    Parameters
    ----------
    value: ndarray
    viewer: "napari.Viewer"

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
    viewer: "napari.Viewer"
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
                if layer is not None:
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
        viewer: "napari.Viewer"
            The viewer is necessary to find out if a string in the argument list corresponds to a layer
            in the viewer.
        """
    for i in range(len(arguments)):
        value = arguments[i]
        if is_image(value):
            if len(value.shape) == 4:
                layer = _get_layer_from_data(viewer, value)
                new_value = value[current_timepoint]
                if new_value.shape[0] == 1:
                    new_value = new_value[0]
                arguments[i] = new_value
                layer.metadata[CURRENT_TIME_FRAME_DATA] = new_value

def is_image(something):
    return hasattr(something, "dtype") and hasattr(something, "shape")
