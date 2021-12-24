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