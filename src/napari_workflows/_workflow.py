import napari
import numpy as np
import inspect
from dask.threaded import get as dask_get
from napari._qt.qthreading import thread_worker
import time

METADATA_WORKFLOW_VALID_KEY = "workflow_valid"

CURRENT_TIME_FRAME_DATA = "current_time_frame_data"


class Workflow():
    """
    The Workflow class encapsulates a dictionary that works as dask-task-graph.
    """

    def __init__(self):
        self._tasks = {}

    def set(self, name, func_or_data, *args, **kwargs):
        if not callable(func_or_data):
            self._tasks[name] = func_or_data
            return

        sig = inspect.signature(func_or_data)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()

        used_args = [value for key, value in bound.arguments.items()]
        for i in range(len(used_args)):
            if callable(used_args[i]):
                used_args[i] = None

        while (used_args[-1] is None):
            used_args = used_args[:-1]

        self._tasks[name] = tuple([func_or_data] + used_args)

    def remove(self, name):
        if name in self._tasks.keys():
            self._tasks.pop(name)

    def get(self, name):
        return dask_get(self._tasks, name)

    def get_task(self, name):
        return self._tasks[name]

    def set_task(self, name, task):
        self._tasks[name] = task

    def remove_all_except(self, names):
        to_remove = [k for k in self._tasks.keys() if k not in names]
        for r in to_remove:
            print("removing ", r)
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
        Return all names of images that are produces out of a given image.
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

    def __str__(self):
        out = "Workflow:\n"
        for result, task in self._tasks.items():
            out = out + result + " <- "+ str(task) + "\n"
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
        self.viewer = viewer
        self.workflow = Workflow()

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

    def _update_invalid_layer(self):
        layer = self._search_first_invalid_layer(self.workflow.roots())
        if layer is None:
            return
        try:
            GUI_KEY = 'magic_gui_widget'
            self.viewer.layers[layer.name].metadata[GUI_KEY]()
            #layer.data = np.asarray(self._compute(layer.name))
            layer.metadata[METADATA_WORKFLOW_VALID_KEY] = True
        except Exception as a:
            print("Error while updating", layer.name, a)

    def _compute(self, name):
        task = list(self.workflow.get_task(name)).copy()
        function = task[0]
        arguments = task[1:]
        for i in range(len(arguments)):
            a = arguments[i]
            if isinstance(a, str):
                if _viewer_has_layer(self.viewer, a):
                    arguments[i] = self.viewer.layers[a].data

        if len(self.viewer.dims.current_step) == 4:
            current_timepoint = self.viewer.dims.current_step[0]
            _break_down_4d_to_2d_args(arguments, current_timepoint, self.viewer)

        return function(*arguments)

    def _search_first_invalid_layer(self, items):
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

    def invalidate(self, items):
        for f in items:
            if _viewer_has_layer(self.viewer, f):
                layer = self.viewer.layers[f]
                layer.metadata[METADATA_WORKFLOW_VALID_KEY] = False
                self.invalidate(self.workflow.followers_of(f))


    def _register_events_to_viewer(self, viewer: napari.Viewer):
        viewer.dims.events.current_step.connect(self._slider_updated)

        viewer.layers.events.inserted.connect(self._layer_added)
        viewer.layers.events.removed.connect(self._layer_removed)
        viewer.layers.selection.events.changed.connect(self._layer_selection_changed)

    def update(self, target_layer, function, *args, **kwargs):
        def _layer_name_or_value(value, viewer):
            layer = _get_layer_from_data(viewer, value)
            if layer is not None:
                return layer.name
            return value

        args = list(args)
        for i in range(len(args)):
            args[i] = _layer_name_or_value(args[i], self.viewer)
        if isinstance(args[-1], napari.Viewer):
            args = args[:-1]
        args = tuple(args)

        self.workflow.set(target_layer.name, function, *args, **kwargs)

        self.remove_zombies()

        # set result valid
        target_layer.metadata[METADATA_WORKFLOW_VALID_KEY] = True
        self.invalidate(self.workflow.followers_of(target_layer.name))

    def remove_zombies(self):
        layer_names = [layer.name for layer in self.viewer.layers]
        self.workflow.remove_all_except(layer_names)

    def to_python_code(self):
        return _generate_python_code(self.workflow, self.viewer)

    def _register_events_to_layer(self, layer):
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
        #print("Layer removed", event.value, type(event.value))
        self.workflow.remove(event.value.name)

    def _slider_updated(self, event):
        slider = event.value
        print("Slider updated", event.value, type(event.value))
        if len(slider) == 4: # a time-slider exists
            for l in self.viewer.layers:
                if len(l.data.shape) == 4:
                    self.invalidate(self.workflow.followers_of(l.name))

    def _layer_selection_changed(self, event):
        pass
        #print("Layer selection changed", event)


def _viewer_has_layer(viewer, name):
    try:
        layer = viewer.layers[name]
        return layer is not None
    except KeyError:
        return False



def _get_layer_from_data(viewer, data):
    """
    Returns the layer in viewer that has the given data
    """
    for layer in viewer.layers:
        if layer.data is data:
            return layer
        try:
            if layer.metadata[CURRENT_TIME_FRAME_DATA] is data:
                return layer
        except KeyError:
            pass
    return None


def _generate_python_code(workflow, viewer):
    imports = []
    code = []

    roots = workflow.roots()

    def better_str(value):
        if isinstance(value, str):
            value = value.replace("[", "_") \
                .replace("]", "_") \
                .replace(" ", "_") \
                .replace("(", "_") \
                .replace(")", "_") \
                .replace(".", "_") \
                .replace("-", "_")
            if value[0] in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
                value = "img_" + value
        return str(value)

    def build_output(list_of_items, func_to_follow):
        for key in list_of_items:
            result_name = better_str(key)
            try:
                task = workflow.get_task(key)
                print("TASK", task)
                function = task[0]
                arguments = task[1:]
                if arguments[-1] is None:
                    arguments = arguments[:-1]

                package_path = function.__module__.split(".")
                module = package_path[0]
                new_import = "import " + module

                loaded_module = __import__(module)
                try:
                    alias = loaded_module.__common_alias__
                    new_import = new_import + " as " + alias

                    if len(package_path) == 1:
                        module = alias
                    else:
                        module = alias + "." + ".".join(package_path[1:])
                except:
                    pass

                if new_import not in imports:
                    imports.append(new_import)
                arg_str = ", ".join([better_str(a) for a in arguments])

                code.append("# " + function.__name__.replace("_", " "))
                code.append(f"{result_name} = {module}.{function.__name__}({arg_str})")
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

    preamble = dedent("""
        import napari

        if 'viewer' not in globals():
            viewer = napari.Viewer()
        """).strip()

    complete_code = "\n".join(imports) + "\n" + preamble + "\n\n" + "\n".join(code) + "\n"

    import autopep8
    complete_code = autopep8.fix_code(complete_code)

    return complete_code



def _layer_invalid(layer):
    try:
        return layer.metadata[METADATA_WORKFLOW_VALID_KEY] == False
    except KeyError:
        return False

def _break_down_4d_to_2d_kwargs(arguments, current_timepoint, viewer):
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

def _break_down_4d_to_2d_args(arguments, current_timepoint, viewer):
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


