from napari_workflows import Workflow

def test_none():
    def identity(x):
        return x

    w = Workflow()
    w.set("x", identity, None)
