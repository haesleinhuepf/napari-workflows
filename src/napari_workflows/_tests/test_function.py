def test_workflows():
    from napari_workflows import Workflow
    from skimage.filters import threshold_otsu, gaussian
    from skimage.measure import label

    w = Workflow()

    # define denoising
    w.set("denoised", gaussian, "input", sigma=2)

    # define segmentation
    def threshold(image):
        return image > threshold_otsu(image)

    w.set("binarized", threshold, "denoised")

    w.set("labeled", label, "binarized")

    # Let's print out the whole workflow
    print(str(w))

    assert len(w._tasks.keys()) == 3


def test_with_viewer(make_napari_viewer):
    viewer = make_napari_viewer()

    import napari
    import numpy as np
    image = np.asarray([
        [0, 0, 0, 0, 0, 0, 0],
        [1, 1, 1, 0, 0, 1, 1],
        [1, 2, 1, 0, 0, 1, 2],
        [1, 1, 1, 0, 0, 1, 1],
        [0, 0, 0, 0, 0, 0, 0],
        [0, 0, 1, 1, 1, 0, 0],
        [0, 0, 1, 2, 1, 0, 0],
    ])

    image_layer = viewer.add_image(image)

    def segment(image:napari.types.ImageData, sigma:float=5)->napari.types.LabelsData:
        return image > 0.5

    def refine(image:napari.types.LabelsData) -> napari.types.LabelsData:
        return image

    from napari_workflows import WorkflowManager
    manager = WorkflowManager.install(viewer)

    from napari_tools_menu import make_gui
    gui = make_gui(segment, viewer, auto_call=True)
    viewer.window.add_dock_widget(gui)
    # invoke execution / workflow update
    gui.sigma.value = gui.sigma.value

    workflow = manager.workflow

    print(workflow)
    print(viewer.layers)

    test_key_root = image_layer.name
    test_key = workflow.followers_of(test_key_root)[0]

    # test analysing workflow
    assert len(workflow._tasks.keys()) == 1
    assert len(workflow.roots()) == 1

    # add one more step
    gui = make_gui(refine, viewer, auto_call=True)
    viewer.window.add_dock_widget(gui)
    # invoke execution / workflow update
    gui.image.value = gui.image.value

    # test analysing workflow
    assert len(workflow._tasks.keys()) == 2
    assert len(workflow.roots()) == 1

    print(workflow)

    # test followers, sources and leafs
    assert len(workflow.followers_of(test_key)) == 1
    assert len(workflow.sources_of(test_key)) == 1
    assert len(workflow.leafs()) == 1

    # test manager
    manager.update(list(viewer.layers)[1], segment, "Image", 2)

    # test code generation
    code = manager.to_python_code()
    print(code)
    assert 14 < len(code.split("\n")) < 18

    # test event handling
    image_layer.data = image

    # test misc utilities
    from napari_workflows._workflow import _get_layer_from_data, _layer_invalid, _viewer_has_layer, _layer_name_or_value, _break_down_4d_to_2d_args, _break_down_4d_to_2d_kwargs

    assert _get_layer_from_data(viewer, image) == image_layer
    assert _layer_invalid(list(viewer.layers)[2])
    assert _viewer_has_layer(viewer, image_layer.name) == True
    assert _viewer_has_layer(viewer, "blub") == False
    assert _layer_name_or_value(image_layer.data, viewer) == image_layer.name
    data = np.asarray([[1,2], [3,4]])
    assert _layer_name_or_value(data, viewer) is data

    # just run those
    _break_down_4d_to_2d_args([np.asarray([[0,1],[5,6]]), "hello", 3, 4], 0, viewer)
    _break_down_4d_to_2d_kwargs({'data':np.asarray([[0,1],[5,6]]), 'name': "hello", 'num1': 3, 'num2':4}, 0, viewer)

    # test removing a layer
    viewer.layers.remove(image_layer)

    # test removing a task
    workflow.remove(test_key)
    assert len(workflow._tasks.keys()) == 1

    # test removing all others
    workflow.remove_all_except(test_key)
    assert len(workflow._tasks.keys()) == 0

